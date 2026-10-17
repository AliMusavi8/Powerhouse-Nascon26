package com.nascon.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Undo
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Flag
import androidx.compose.material.icons.filled.HourglassTop
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.ShoppingBag
import androidx.compose.material.icons.filled.SportsScore
import androidx.compose.material.icons.filled.Timeline
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.nascon.app.data.Messages
import com.nascon.app.data.Outcome
import com.nascon.app.data.arr
import com.nascon.app.data.bool
import com.nascon.app.data.int
import com.nascon.app.data.jobj
import com.nascon.app.data.json
import com.nascon.app.data.long
import com.nascon.app.data.money
import com.nascon.app.data.obj
import com.nascon.app.data.str
import com.nascon.app.data.strings
import com.nascon.app.graph
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener

@Composable
fun MatchScreen(matchId: String) {
    val g = graph()
    val ui = LocalUi.current
    val res = rememberRes("/api/v1/matches/$matchId")
    var liveConnected by remember { mutableStateOf(false) }

    // Live updates: re-fetch on every server push; reconnect while the screen is open.
    DisposableEffect(matchId, ui.session.token) {
        var closed = false
        var socket: WebSocket? = null
        val handler = android.os.Handler(android.os.Looper.getMainLooper())
        fun connect() {
            if (closed) return
            val url = g.api.base().replaceFirst("http", "ws") + "/ws/matches/$matchId?token=${ui.session.token}"
            socket = g.api.client.newWebSocket(Request.Builder().url(url).build(), object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) { handler.post { liveConnected = true } }
                override fun onMessage(webSocket: WebSocket, text: String) {
                    val type = try { json.parseToJsonElement(text).jsonObject.str("type") } catch (e: Exception) { null }
                    if (type == "match_updated" || type == "product_pinned") handler.post { res.reload() }
                }
                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    handler.post { liveConnected = false }
                    handler.postDelayed({ connect() }, 4000)
                }
                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) { handler.post { liveConnected = false } }
            })
        }
        connect()
        onDispose { closed = true; handler.removeCallbacksAndMessages(null); socket?.close(1000, null) }
    }

    val queued by g.db.actions().observeAll().collectAsStateWithLifecycle(emptyList())
    val pendingHere = queued.filter {
        it.state == com.nascon.app.data.PendingAction.STATE_PENDING && it.type == "score_event" &&
            json.parseToJsonElement(it.action).jsonObject.obj("payload")?.str("match_id") == matchId
    }
    val m = res.loaded?.data
    var tab by androidx.compose.runtime.saveable.rememberSaveable { mutableStateOf(0) }
    Page(
        "Match Details", back = true, savedAt = res.loaded?.savedAt,
        actions = { if (m?.str("status") == "in_progress") BadgePill("Live", dot = true, inverted = false) },
        hero = { m?.let { HeroScore(it, liveConnected && res.loaded?.fromCache == false) } },
    ) {
        ResBox(res) { l ->
            val d = l.data
            val canScore = d.bool("can_score") && ui.session.canScore
            Column(Modifier.fillMaxSize()) {
                PillTabs(listOf("Timeline", "Stats"), tab) { tab = it }
                LazyColumn(Modifier.weight(1f)) {
                    if (tab == 1) {
                        item { StatsCard(d) }
                    } else {
                        d.obj("pinned_product")?.let { p -> item { PinnedProduct(p) { ui.nav.navigate("product/${p.str("product_id")}") } } }
                        item { SectionLabel("Time Line") }
                        val events = d.arr("events").reversed()
                        if (events.isEmpty() && pendingHere.isEmpty()) item {
                            Empty(Icons.Filled.Timeline, "No events yet", if (d.str("status") == "upcoming") "The match hasn't started." else "Events appear here as they happen.")
                        } else item {
                            BigCard {
                                pendingHere.forEach { a ->
                                    Row(Modifier.fillMaxWidth().background(extra.warnBg).heightIn(min = 52.dp).padding(horizontal = 16.dp, vertical = 8.dp),
                                        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                        Icon(Icons.Filled.HourglassTop, contentDescription = null, tint = extra.warn, modifier = Modifier.size(18.dp))
                                        Column(Modifier.weight(1f)) {
                                            Text(a.title, fontWeight = FontWeight.Medium)
                                            Text("Pending · saved offline at ${time(a.createdAt)}", fontSize = 12.sp, color = extra.warn)
                                        }
                                    }
                                    CardDivider()
                                }
                                events.forEachIndexed { i, e -> EventRow(e, d, last = i == events.lastIndex) }
                            }
                        }
                    }
                    item { Box(Modifier.height(16.dp)) }
                }
                if (canScore) OrganiserBar(matchId, d) { res.reload() }
            }
        }
    }
}

@Composable
private fun HeroScore(d: JsonObject, live: Boolean) {
    val home = d.obj("home")
    val away = d.obj("away")
    val status = d.str("status")
    fun scoreText(s: JsonObject?) = buildString {
        append(s?.int("score") ?: 0)
        s?.int("wickets")?.let { append("/$it") }
    }
    val white = androidx.compose.ui.graphics.Color.White
    val soft = white.copy(alpha = 0.75f)
    val desc = "${home?.str("name")} ${scoreText(home)}, ${away?.str("name")} ${scoreText(away)}. " + statusText(status, d)
    Row(Modifier.fillMaxWidth().semantics(mergeDescendants = true) { contentDescription = desc }, verticalAlignment = Alignment.CenterVertically) {
        TeamBlock(home?.str("name") ?: "", Modifier.weight(1f), crest = 58, color = white)
        Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.padding(horizontal = 4.dp)) {
            Text(if (status == "upcoming") "vs" else "${scoreText(home)}-${scoreText(away)}", style = ScoreStyle, color = white)
            if (home?.str("overs") != null) Text("${home.str("overs")} ov · ${away?.str("overs")} ov", fontSize = 12.sp, color = soft)
            Text(statusText(status, d), fontSize = 12.sp, color = soft)
            parseTime(d.str("scheduled_at"))?.let { Text("${dayLabel(it)} · ${clock(it)}", fontSize = 12.sp, color = soft) }
            d.str("venue")?.let { Text(it, fontSize = 12.sp, color = soft, textAlign = TextAlign.Center) }
            if (status == "in_progress") Text(if (live) "Live updates on" else "Reconnecting…", fontSize = 11.sp, color = soft)
        }
        TeamBlock(away?.str("name") ?: "", Modifier.weight(1f), crest = 58, color = white)
    }
}

/** Team stats derived from the event log; rows come from the sport's own scoring events. */
@Composable
private fun StatsCard(d: JsonObject) {
    val home = d.obj("home")
    val away = d.obj("away")
    val hid = home?.str("team_id")
    val aid = away?.str("team_id")
    val live = d.arr("events").filter { !it.bool("compensated") }
    fun count(type: String, et: String? = null, team: String?) = live.count {
        it.str("type") == type && it.obj("payload")?.str("team_id") == team && (et == null || it.obj("payload")?.str("event_type") == et)
    }
    fun sumDisc(team: String?) = live.filter { it.str("type") == "discipline" && it.obj("payload")?.str("team_id") == team }.sumOf { it.obj("payload")?.int("points") ?: 0 }
    val rows = buildList {
        add(Triple("Score", (home?.int("score") ?: 0).toString(), (away?.int("score") ?: 0).toString()))
        d.strings("scoring_events").forEach { et -> add(Triple(Messages.label(et), count("score", et, hid).toString(), count("score", et, aid).toString())) }
        if (home?.int("wickets") != null) add(Triple("Wickets", home.int("wickets").toString(), (away?.int("wickets") ?: 0).toString()))
        if (home?.str("overs") != null) add(Triple("Overs", home.str("overs") ?: "0", away?.str("overs") ?: "0"))
        add(Triple("Discipline points", sumDisc(hid).toString(), sumDisc(aid).toString()))
        add(Triple("Corrections", live.count { it.str("type") == "compensation" }.toString(), ""))
    }
    Column {
        Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
            BigCrest(home?.str("name") ?: "", 36)
            Text("TEAM STATS", Modifier.weight(1f), textAlign = TextAlign.Center, fontWeight = FontWeight.Medium, letterSpacing = 0.5.sp)
            BigCrest(away?.str("name") ?: "", 36)
        }
        rows.forEach { (label, l, r) ->
            val ln = l.toDoubleOrNull()
            val rn = r.toDoubleOrNull()
            val lBest = ln != null && rn != null && ln > rn
            val rBest = ln != null && rn != null && rn > ln
            Row(Modifier.fillMaxWidth().heightIn(min = 44.dp).padding(horizontal = 20.dp)
                .semantics(mergeDescendants = true) { contentDescription = "$label: ${home?.str("name")} $l, ${away?.str("name")} $r" },
                verticalAlignment = Alignment.CenterVertically) {
                Text(l, Modifier.width(56.dp), color = if (lBest) extra.link else MaterialTheme.colorScheme.onSurface,
                    fontWeight = if (lBest) FontWeight.Bold else FontWeight.Normal, fontSize = 15.sp)
                Text(label, Modifier.weight(1f), textAlign = TextAlign.Center, fontSize = 15.sp)
                Text(r, Modifier.width(56.dp), textAlign = TextAlign.End, color = if (rBest) extra.link else MaterialTheme.colorScheme.onSurface,
                    fontWeight = if (rBest) FontWeight.Bold else FontWeight.Normal, fontSize = 15.sp)
            }
        }
        Box(Modifier.height(8.dp))
    }
}

private fun teamName(d: JsonObject, teamId: String?): String = when (teamId) {
    d.obj("home")?.str("team_id") -> d.obj("home")?.str("name") ?: "Home"
    d.obj("away")?.str("team_id") -> d.obj("away")?.str("name") ?: "Away"
    else -> teamId ?: ""
}

private fun statusText(status: String?, d: JsonObject): String = when (status) {
    "completed" -> when (d.str("outcome")) {
        "draw" -> "Match drawn"
        null, "undecided" -> "Full time"
        else -> d.str("winner_team_id")?.let { "${teamName(d, it)} won" } ?: "Full time"
    }
    "in_progress" -> "In progress"
    else -> "Not started"
}

@Composable
private fun PinnedProduct(p: JsonObject, onBuy: () -> Unit) {
    val v = p.arr("variants").firstOrNull()
    SectionLabel("Pinned by the club")
    BigCard(onClick = onBuy) {
        Row(Modifier.fillMaxWidth().padding(14.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Box(Modifier.size(56.dp).clip(RoundedCornerShape(18.dp)).background(MaterialTheme.colorScheme.primary.copy(alpha = 0.1f)), contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.ShoppingBag, null, tint = MaterialTheme.colorScheme.primary)
            }
            Column(Modifier.weight(1f)) {
                Text(p.str("name") ?: "", fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(money(v?.long("price_minor"), v?.str("currency")), color = extra.muted)
            }
            Button(onClick = onBuy, modifier = Modifier.heightIn(min = 48.dp)) { Text("Buy") }
        }
    }
}

@Composable
private fun EventRow(e: JsonObject, d: JsonObject, last: Boolean = false) {
    val p = e.obj("payload") ?: JsonObject(emptyMap())
    val type = e.str("type")
    val compensated = e.bool("compensated")
    val (title, sub) = when (type) {
        "score" -> Messages.label(p.str("event_type")) to teamName(d, p.str("team_id"))
        "discipline" -> "Discipline" to "${teamName(d, p.str("team_id"))} · ${p.int("points") ?: 0} fair-play points"
        "compensation" -> "Correction" to (p.str("reason") ?: "Earlier event reversed")
        "tiebreak_winner" -> "Tie-break winner" to teamName(d, p.str("team_id"))
        "match_start" -> "Match started" to ""
        "match_end" -> "Match ended" to ""
        else -> Messages.label(type) to ""
    }
    Column {
        Row(Modifier.fillMaxWidth().heightIn(min = 52.dp).padding(horizontal = 16.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("#${e.int("sequence") ?: ""}", style = NumStyle, color = extra.muted, modifier = Modifier.width(32.dp))
            Icon(when (type) { "compensation" -> Icons.AutoMirrored.Filled.Undo; "match_start" -> Icons.Filled.PlayArrow; "match_end" -> Icons.Filled.Flag; else -> Icons.Filled.SportsScore },
                contentDescription = null, tint = extra.muted, modifier = Modifier.size(18.dp))
            Column(Modifier.weight(1f)) {
                Text(title, fontWeight = FontWeight.Medium, textDecoration = if (compensated) TextDecoration.LineThrough else null,
                    color = if (compensated) extra.muted else MaterialTheme.colorScheme.onSurface)
                if (sub.isNotBlank()) Text(sub, fontSize = 12.sp, color = extra.muted)
            }
            if (compensated) Chip("Corrected", extra.muted, MaterialTheme.colorScheme.surfaceVariant)
        }
        if (!last) CardDivider()
    }
}

/** League organiser tools. Event types come from the sport config sent by the server. */
@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
private fun OrganiserBar(matchId: String, d: JsonObject, refresh: () -> Unit) {
    val g = graph()
    val ui = LocalUi.current
    val scope = rememberCoroutineScope()
    val status = d.str("status")
    val version = d.int("version") ?: 0
    val home = d.obj("home")
    val away = d.obj("away")
    var addOpen by remember { mutableStateOf(false) }
    var correctOpen by remember { mutableStateOf(false) }
    var confirmEnd by remember { mutableStateOf(false) }
    var confirmStart by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }

    fun send(type: String, payload: JsonObject, title: String) {
        busy = true
        scope.launch {
            val out = g.sync.scoreEvent(matchId, version, type, payload, title)
            busy = false
            ui.toast(if (out is Outcome.Done) "$title recorded." else out.message)
            if (out is Outcome.Done) refresh()
        }
    }

    Column(Modifier.background(MaterialTheme.colorScheme.surface)) {
        CardDivider()
        Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Box(Modifier.weight(1f))
            when (status) {
                "upcoming" -> Button(onClick = { confirmStart = true }, enabled = !busy, modifier = Modifier.heightIn(min = 48.dp)) {
                    Icon(Icons.Filled.PlayArrow, null); Text(" Start match")
                }
                "in_progress" -> {
                    OutlinedButton(onClick = { correctOpen = true }, enabled = !busy, modifier = Modifier.heightIn(min = 48.dp)) { Text("Correct") }
                    OutlinedButton(onClick = { confirmEnd = true }, enabled = !busy, modifier = Modifier.heightIn(min = 48.dp)) { Text("End") }
                    Button(onClick = { addOpen = true }, enabled = !busy, modifier = Modifier.heightIn(min = 48.dp)) {
                        Icon(Icons.Filled.Add, null); Text(" Event")
                    }
                }
                else -> OutlinedButton(onClick = { correctOpen = true }, enabled = !busy, modifier = Modifier.heightIn(min = 48.dp)) { Text("Correct an event") }
            }
        }
    }

    if (confirmStart) Confirm("Start the match?", "The match will show as live for everyone.", "Start",
        onDismiss = { confirmStart = false }) { confirmStart = false; send("match_start", JsonObject(emptyMap()), "Match start") }
    if (confirmEnd) Confirm("End the match?", "The result becomes final and the table updates.", "End match",
        onDismiss = { confirmEnd = false }) { confirmEnd = false; send("match_end", JsonObject(emptyMap()), "Match end") }

    if (addOpen) {
        var team by remember { mutableStateOf(0) }
        val teams = listOf(home, away)
        val eventTypes = d.strings("scoring_events")
        AlertDialog(
            onDismissRequest = { addOpen = false },
            title = { Text("Add event") },
            text = {
                Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                        teams.forEachIndexed { i, t ->
                            SegmentedButton(selected = team == i, onClick = { team = i }, shape = SegmentedButtonDefaults.itemShape(i, 2),
                                modifier = Modifier.heightIn(min = 48.dp)) {
                                Text(t?.str("name") ?: "", maxLines = 1, overflow = TextOverflow.Ellipsis)
                            }
                        }
                    }
                    Text("Score", style = MaterialTheme.typography.labelSmall, color = extra.muted)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        eventTypes.forEach { et ->
                            FilledTonalButton(onClick = {
                                addOpen = false
                                val t = teams[team]
                                send("score", jobj("team_id" to t?.str("team_id"), "event_type" to et), "${Messages.label(et)} for ${t?.str("name")}")
                            }, modifier = Modifier.heightIn(min = 48.dp)) { Text(Messages.label(et)) }
                        }
                    }
                    Text("Other", style = MaterialTheme.typography.labelSmall, color = extra.muted)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(onClick = {
                            addOpen = false
                            val t = teams[team]
                            send("discipline", jobj("team_id" to t?.str("team_id"), "points" to 1), "Discipline point for ${t?.str("name")}")
                        }, modifier = Modifier.heightIn(min = 48.dp)) { Text("Discipline point") }
                        OutlinedButton(onClick = {
                            addOpen = false
                            val t = teams[team]
                            send("tiebreak_winner", jobj("team_id" to t?.str("team_id")), "Tie-break win for ${t?.str("name")}")
                        }, modifier = Modifier.heightIn(min = 48.dp)) { Text("Tie-break winner") }
                    }
                }
            },
            confirmButton = {},
            dismissButton = { TextButton(onClick = { addOpen = false }, modifier = Modifier.heightIn(min = 48.dp)) { Text("Close") } },
        )
    }

    if (correctOpen) {
        val candidates = d.arr("events").filter { !it.bool("compensated") && it.str("type") in setOf("score", "discipline", "tiebreak_winner") }.reversed()
        var pick by remember { mutableStateOf<String?>(null) }
        var reason by remember { mutableStateOf("") }
        AlertDialog(
            onDismissRequest = { correctOpen = false },
            title = { Text("Correct an event") },
            text = {
                Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    if (candidates.isEmpty()) Text("There are no events that can be corrected.")
                    Text("The original stays in the timeline, marked as corrected.", fontSize = 13.sp, color = extra.muted)
                    candidates.forEach { e ->
                        val p = e.obj("payload")
                        val label = "#${e.int("sequence")} " + when (e.str("type")) {
                            "score" -> "${Messages.label(p?.str("event_type"))} · ${teamName(d, p?.str("team_id"))}"
                            "discipline" -> "Discipline · ${teamName(d, p?.str("team_id"))}"
                            else -> "Tie-break · ${teamName(d, p?.str("team_id"))}"
                        }
                        Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).selectable(pick == e.str("event_id"), role = Role.RadioButton) { pick = e.str("event_id") },
                            verticalAlignment = Alignment.CenterVertically) {
                            RadioButton(selected = pick == e.str("event_id"), onClick = null)
                            Text(label, Modifier.padding(start = 8.dp))
                        }
                    }
                    OutlinedTextField(reason, { reason = it }, label = { Text("Reason") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                }
            },
            confirmButton = {
                Button(onClick = {
                    correctOpen = false
                    send("compensation", jobj("compensates" to pick, "reason" to reason.ifBlank { "Correction by organiser" }), "Correction")
                }, enabled = pick != null, modifier = Modifier.heightIn(min = 48.dp)) { Text("Reverse event") }
            },
            dismissButton = { TextButton(onClick = { correctOpen = false }, modifier = Modifier.heightIn(min = 48.dp)) { Text("Cancel") } },
        )
    }
}
