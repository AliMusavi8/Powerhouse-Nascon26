package com.nascon.app.data

import androidx.compose.ui.graphics.Color
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject

data class User(
    val id: String,
    val email: String,
    val name: String,
    val role: String,
    val tenantId: String?,
    val leagueId: String?,
    val clubId: String?,
    val playerId: String?,
) {
    val roleLabel
        get() = when (role) {
            "super_admin" -> "Platform admin"
            "league_organizer" -> "League organiser"
            "club_manager" -> "Club manager"
            "player" -> "Player"
            else -> "Viewer"
        }
}

data class Branding(val name: String, val primary: Color, val secondary: Color, val logoText: String)

data class SessionState(val token: String, val user: User, val branding: Branding, val canScore: Boolean, val canManage: Boolean)

/** Signed-in account. Accounts are remembered (encrypted) so a known user can reopen the app offline. */
class Session(private val store: SecureStore) {
    private val _state = MutableStateFlow<SessionState?>(null)
    val state: StateFlow<SessionState?> = _state
    val current get() = _state.value

    fun restore() {
        val email = store.get("active") ?: return
        val acct = store.get("acct:$email")?.let { json.parseToJsonElement(it).jsonObject } ?: return
        _state.value = build(acct)
    }

    fun signIn(email: String, password: String, login: JsonObject, me: JsonObject?) {
        val acct = jobj(
            "token" to login.str("token"),
            "user" to login.obj("user"),
            "me" to me,
            "pw" to SecureStore.hash(email, password),
        )
        val key = email.lowercase()
        store.put("acct:$key", acct.toString())
        store.put("token:$key", login.str("token") ?: "")
        store.put("active", key)
        _state.value = build(acct)
    }

    /** Offline sign-in for an account that signed in on this device before. */
    fun signInOffline(email: String, password: String): Boolean {
        val key = email.lowercase()
        val acct = store.get("acct:$key")?.let { json.parseToJsonElement(it).jsonObject } ?: return false
        if (acct.str("pw") != SecureStore.hash(email, password)) return false
        store.put("active", key)
        _state.value = build(acct)
        return true
    }

    fun updateMe(me: JsonObject) {
        val s = current ?: return
        val key = s.user.email.lowercase()
        val acct = store.get("acct:$key")?.let { json.parseToJsonElement(it).jsonObject } ?: return
        val next = JsonObject(acct + ("me" to me))
        store.put("acct:$key", next.toString())
        _state.value = build(next)
    }

    fun signOut() {
        store.remove("active")
        _state.value = null
    }

    fun tokenFor(owner: String): String? = store.get("token:${owner.lowercase()}")?.takeIf { it.isNotBlank() }

    private fun build(acct: JsonObject): SessionState {
        val u = acct.obj("user") ?: JsonObject(emptyMap())
        val me = acct.obj("me")
        val tenant = me?.obj("tenant")
        val b = tenant?.obj("branding")
        val perms = me?.obj("permissions")
        val role = u.str("role") ?: "viewer"
        val user = User(
            id = u.str("user_id") ?: u.str("email") ?: "",
            email = u.str("email") ?: "",
            name = u.str("name") ?: u.str("email") ?: "",
            role = role,
            tenantId = u.str("tenant_id"),
            leagueId = u.str("league_id"),
            clubId = u.str("club_id"),
            playerId = u.str("player_id"),
        )
        return SessionState(
            token = acct.str("token") ?: "",
            user = user,
            branding = Branding(
                name = tenant?.str("name") ?: "Alpha Sports",
                primary = parseColor(b?.str("primary_color")) ?: Color(0xFF1E4FD8),
                secondary = parseColor(b?.str("secondary_color")) ?: Color(0xFFF5B700),
                logoText = b?.str("logo_text") ?: "AS",
            ),
            canScore = perms?.bool("score_entry") ?: (role == "league_organizer" || role == "super_admin"),
            canManage = perms?.bool("roster_management") ?: (role == "club_manager" || role == "super_admin"),
        )
    }

    private fun parseColor(hex: String?): Color? = try {
        hex?.removePrefix("#")?.let { Color(("FF" + it).toLong(16)) }
    } catch (e: Exception) {
        null
    }
}
