package com.nascon.app.data

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.nascon.app.App
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import java.util.UUID

/** Tracks whether the phone has a usable network. */
class NetworkMonitor(context: Context, private val onRegained: () -> Unit) {
    private val cm = context.getSystemService(ConnectivityManager::class.java)
    private val _online = MutableStateFlow(check())
    val online: StateFlow<Boolean> = _online

    init {
        val req = NetworkRequest.Builder().addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET).build()
        cm.registerNetworkCallback(req, object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) = update()
            override fun onLost(network: Network) = update()
            override fun onCapabilitiesChanged(network: Network, caps: NetworkCapabilities) = update()
        })
    }

    private fun check(): Boolean {
        val caps = cm.getNetworkCapabilities(cm.activeNetwork) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }

    private fun update() {
        val was = _online.value
        _online.value = check()
        if (!was && _online.value) onRegained()
    }
}

sealed class Outcome(val message: String) {
    class Done(message: String, val data: JsonObject? = null) : Outcome(message)
    class Queued(message: String) : Outcome(message)
    class Failed(message: String) : Outcome(message)
}

/** Sends score and roster actions online, or stores them in the offline queue in the /sync action format. */
class SyncManager(
    private val context: Context,
    private val api: Api,
    private val db: AppDb,
    private val session: Session,
    private val settings: Settings,
) {
    private val mutex = Mutex()
    private val _syncing = MutableStateFlow(false)
    val syncing: StateFlow<Boolean> = _syncing
    private val _lastSummary = MutableStateFlow<String?>(null)
    val lastSummary: StateFlow<String?> = _lastSummary

    lateinit var network: NetworkMonitor

    suspend fun scoreEvent(matchId: String, version: Int, type: String, payload: JsonObject, title: String): Outcome {
        val eventId = newId("ev")
        val online = jobj("event_id" to eventId, "type" to type, "payload" to payload)
        val queued = jobj("event_id" to eventId, "match_id" to matchId, "type" to type, "payload" to payload)
        return send(title, "score_event", version, queued) { api.post("/api/v1/matches/$matchId/events", online) }
    }

    suspend fun rosterAction(
        clubId: String, leagueId: String, playerId: String, type: String, toSquadId: String?,
        effectiveDate: String, loanEndDate: String?, reason: String, baseVersion: Int, title: String,
    ): Outcome {
        val requestId = newId("rq")
        val online = jobj(
            "request_id" to requestId, "type" to type, "player_id" to playerId, "to_squad_id" to toSquadId,
            "effective_date" to effectiveDate, "loan_end_date" to loanEndDate, "reason" to reason,
        )
        val queued = jobj(
            "request_id" to requestId, "league_id" to leagueId, "player_id" to playerId, "type" to type,
            "from_squad_id" to clubId, "to_squad_id" to toSquadId, "effective_date" to effectiveDate,
            "loan_end_date" to loanEndDate, "reason" to reason, "requested_by" to session.current?.user?.email,
        )
        return send(title, "roster_transfer", baseVersion, queued) { api.post("/api/v1/clubs/$clubId/roster/transfer", online) }
    }

    private suspend fun send(title: String, type: String, base: Int, payload: JsonObject, call: suspend () -> JsonObject): Outcome {
        if (network.online.value) {
            try {
                return Outcome.Done("Saved.", call())
            } catch (e: ApiError) {
                if (!e.isNetwork) return Outcome.Failed(e.message)
            }
        }
        val owner = session.current?.user?.email ?: return Outcome.Failed("Please sign in again.")
        val actionId = newId("act")
        val action = jobj(
            "action_id" to actionId, "type" to type, "queued_at" to nowIso(),
            "base_version" to base, "payload" to payload,
        )
        db.actions().put(PendingAction(actionId, owner, type, title, action.toString(), System.currentTimeMillis()))
        schedule()
        return Outcome.Queued("You're offline. Saved on this phone and will send when you reconnect.")
    }

    fun schedule() {
        val req = OneTimeWorkRequestBuilder<SyncWorker>()
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork("sync", ExistingWorkPolicy.REPLACE, req)
    }

    /** Replays every pending action, grouped by the account that created it. Returns false to retry later. */
    suspend fun syncNow(): Boolean = mutex.withLock {
        val pending = db.actions().pending()
        if (pending.isEmpty()) return true
        _syncing.value = true
        var ok = true
        var applied = 0
        var rejected = 0
        try {
            for ((owner, group) in pending.groupBy { it.owner }) {
                val token = session.tokenFor(owner)
                val body = jobj(
                    "device_id" to settings.deviceId,
                    "actions" to JsonArray(group.map { json.parseToJsonElement(it.action).jsonObject }),
                )
                val res = try {
                    api.post("/api/v1/sync", body, auth = token)
                } catch (e: ApiError) {
                    if (e.isNetwork || e.code == "RATE_LIMITED" || e.code == "SERVER") {
                        ok = false
                        continue
                    }
                    val msg = if (e.status == 401) "Not sent: that account's session ended. Sign in again and redo it."
                    else "Not applied: " + e.message.replaceFirstChar { it.lowercase() }
                    group.forEach { db.actions().resolve(it.actionId, PendingAction.STATE_REJECTED, msg, now()) }
                    rejected += group.size
                    continue
                }
                val byId = res.arr("results").associateBy { it.str("action_id") }
                for (a in group) {
                    val r = byId[a.actionId] ?: continue
                    val status = r.str("status") ?: "rejected"
                    val msg = when (status) {
                        "applied" -> if (r.str("resolution") == "rebased_append")
                            "Applied. It was added after newer changes on the server." else "Applied."
                        "duplicate" -> "Already recorded, nothing changed."
                        else -> "Not applied. " + Messages.forCode(r.str("error_code"))
                    }
                    if (status == "rejected") rejected++ else applied++
                    db.actions().resolve(a.actionId, status, msg, now())
                }
            }
        } finally {
            _syncing.value = false
        }
        if (applied + rejected > 0) {
            _lastSummary.value = buildString {
                append("Synced: $applied applied")
                if (rejected > 0) append(", $rejected not applied")
                append(".")
            }
        }
        ok
    }

    fun clearSummary() {
        _lastSummary.value = null
    }

    companion object {
        fun newId(prefix: String) = prefix + "-" + UUID.randomUUID().toString().replace("-", "").take(16)
        fun now() = System.currentTimeMillis()
        fun nowIso(): String = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US)
            .apply { timeZone = TimeZone.getTimeZone("UTC") }.format(Date())
        fun today(): String = SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date())
    }
}

class SyncWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val sync = (applicationContext as App).graph.sync
        return if (sync.syncNow()) Result.success() else Result.retry()
    }
}
