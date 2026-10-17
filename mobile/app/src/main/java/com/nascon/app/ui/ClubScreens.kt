package com.nascon.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
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
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Groups
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Place
import androidx.compose.material.icons.filled.Shield
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.PrimaryTabRow
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.nascon.app.data.ApiError
import com.nascon.app.data.Messages
import com.nascon.app.data.Outcome
import com.nascon.app.data.PendingAction
import com.nascon.app.data.SyncManager
import com.nascon.app.data.arr
import com.nascon.app.data.bool
import com.nascon.app.data.dbl
import com.nascon.app.data.jobj
import com.nascon.app.data.json
import com.nascon.app.data.obj
import com.nascon.app.data.str
import com.nascon.app.graph
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import java.time.LocalDate

@Composable
fun ClubTab() {
    val ui = LocalUi.current
    val own = ui.session.user.clubId
    if (own != null) {
        ClubScreen(own, back = false); return
    }
    val res = rememberRes("/api/v1/clubs")
    Page("Clubs", savedAt = res.loaded?.savedAt) {
        ResBox(res) { l ->
            val clubs = l.data.arr("clubs")
            if (clubs.isEmpty()) {
                Empty(Icons.Filled.Shield, "No clubs yet", "Clubs appear here once they're registered."); return@ResBox
            }
            LazyColumn(Modifier.fillMaxSize()) {
                item { SectionLabel("${clubs.size} clubs") }
                items(clubs, key = { it.str("club_id") ?: "" }) { c ->
                    RowItem(onClick = { ui.nav.navigate("clubs/${c.str("club_id")}") }) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            Crest(c.str("name") ?: "", 32)
                            Text(c.str("name") ?: "", fontWeight = FontWeight.Medium)
                        }
                    }
                    Divider()
                }
            }
        }
    }
}

@Composable
fun ClubScreen(clubId: String, back: Boolean) {
    val g = graph()
    val ui = LocalUi.current
    val res = rememberRes("/api/v1/clubs/$clubId")
    var tab by rememberSaveable { mutableStateOf(0) }
    var addOpen by remember { mutableStateOf(false) }
    val actions by g.db.actions().observeAll().collectAsStateWithLifecycle(emptyList())
    val pendingPlayers = actions.filter { it.state == PendingAction.STATE_PENDING && it.type == "roster_transfer" }
        .mapNotNull { json.parseToJsonElement(it.action).jsonObject.obj("payload")?.str("player_id") }.toSet()
    val d = res.loaded?.data
    val canManage = (d?.bool("can_manage") ?: false) && ui.session.canManage

    Page(d?.str("name") ?: "Club", back = back, savedAt = res.loaded?.savedAt) {
        Box(Modifier.fillMaxSize()) {
            ResBox(res) { l ->
                val c = l.data
                Column(Modifier.fillMaxSize()) {
                    Row(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface).padding(16.dp),
                        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                        Crest(c.str("name") ?: "", 48)
                        Column {
                            Text(c.str("name") ?: "", style = MaterialTheme.typography.titleMedium)
                            Text(listOfNotNull(c.obj("home_venue")?.str("name"), c.obj("tenant")?.str("name")).joinToString(" · "),
                                fontSize = 13.sp, color = extra.muted)
                        }
                    }
                    PrimaryTabRow(selectedTabIndex = tab, containerColor = MaterialTheme.colorScheme.surface) {
                        listOf("Roster", "Info", "Moves").forEachIndexed { i, t ->
                            Tab(selected = tab == i, onClick = { tab = i }, text = { Text(t) }, modifier = Modifier.heightIn(min = 48.dp))
                        }
                    }
                    when (tab) {
                        0 -> Roster(c, clubId, canManage, pendingPlayers) { res.reload() }
                        1 -> Info(c)
                        else -> Moves(c)
                    }
                }
            }
            if (canManage && tab == 0) ExtendedFloatingActionButton(
                onClick = { addOpen = true },
                icon = { Icon(Icons.Filled.Add, null) }, text = { Text("Add player") },
                modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp),
            )
        }
    }
    if (addOpen) AddPlayerDialog(clubId, onDone = { addOpen = false; res.reload() }, onDismiss = { addOpen = false })
}

private val roles = listOf("starter", "substitute", "captain", "vice_captain")

@Composable
private fun AddPlayerDialog(clubId: String, onDone: () -> Unit, onDismiss: () -> Unit) {
    val g = graph()
    val ui = LocalUi.current
    val scope = rememberCoroutineScope()
    var name by remember { mutableStateOf("") }
    var position by remember { mutableStateOf("") }
    var role by remember { mutableStateOf("substitute") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Add player") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(name, { name = it }, label = { Text("Full name") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(position, { position = it }, label = { Text("Position") }, singleLine = true,
                    supportingText = { Text("For example the short code your league uses") }, modifier = Modifier.fillMaxWidth())
                Text("Role", style = MaterialTheme.typography.labelSmall, color = extra.muted)
                roles.forEach { r ->
                    Row(Modifier.fillMaxWidth().heightIn(min = 44.dp).selectable(role == r, role = Role.RadioButton) { role = r },
                        verticalAlignment = Alignment.CenterVertically) {
                        RadioButton(selected = role == r, onClick = null); Text(Messages.label(r), Modifier.padding(start = 8.dp))
                    }
                }
                error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = {
            Button(enabled = !busy && name.isNotBlank() && position.isNotBlank(), modifier = Modifier.heightIn(min = 48.dp), onClick = {
                busy = true
                scope.launch {
                    try {
                        g.api.post("/api/v1/clubs/$clubId/players", jobj("name" to name.trim(), "position" to position.trim(), "role" to role))
                        ui.toast("${name.trim()} added to the roster.")
                        onDone()
                    } catch (e: ApiError) {
                        error = if (e.isNetwork) "Adding a player needs a connection. Transfers, loans and releases work offline." else e.message
                    } finally { busy = false }
                }
            }) { Text("Add") }
        },
        dismissButton = { TextButton(onClick = onDismiss, modifier = Modifier.heightIn(min = 48.dp)) { Text("Cancel") } },
    )
}

@Composable
private fun Roster(c: JsonObject, clubId: String, canManage: Boolean, pending: Set<String>, refresh: () -> Unit) {
    val roster = c.arr("roster")
    var action by remember { mutableStateOf<Pair<JsonObject, String>?>(null) }
    if (roster.isEmpty()) {
        Empty(Icons.Filled.Groups, "No players yet", if (canManage) "Add your first player with the button below." else "The club hasn't registered any players.")
        return
    }
    LazyColumn(Modifier.fillMaxSize()) {
        item { SectionLabel("${roster.size} players") }
        items(roster, key = { it.str("player_id") ?: "" }) { p ->
            var menu by remember { mutableStateOf(false) }
            val pid = p.str("player_id") ?: ""
            Row(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface).heightIn(min = 56.dp).padding(start = 16.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Text((p.str("position") ?: "").uppercase().take(3), style = NumStyle, color = extra.muted, modifier = Modifier.width(34.dp))
                Column(Modifier.weight(1f).padding(vertical = 8.dp)) {
                    Text(p.str("name") ?: "", fontWeight = FontWeight.Medium, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    val sub = buildList {
                        add(Messages.label(p.str("role")))
                        if (p.str("registration_type") == "loan") add("On loan until ${p.str("loan_end_date") ?: "?"}")
                    }.joinToString(" · ")
                    Text(sub, fontSize = 12.sp, color = extra.muted)
                }
                if (pid in pending) Chip("Pending", extra.warn, extra.warnBg)
                else if (p.str("registration_type") == "loan") Chip("Loan", extra.warn, extra.warnBg)
                else if (p.str("role") == "captain") Chip("Captain", extra.muted, MaterialTheme.colorScheme.surfaceVariant)
                if (canManage) Box {
                    IconButton(onClick = { menu = true }) { Icon(Icons.Filled.MoreVert, contentDescription = "Actions for ${p.str("name")}") }
                    DropdownMenu(menu, onDismissRequest = { menu = false }) {
                        listOf("transfer" to "Transfer", "loan" to "Loan out", "release" to "Release").forEach { (t, label) ->
                            DropdownMenuItem(text = { Text(label) }, onClick = { menu = false; action = p to t }, modifier = Modifier.heightIn(min = 48.dp))
                        }
                    }
                } else Box(Modifier.width(8.dp))
            }
            Divider()
        }
        item { Box(Modifier.height(88.dp)) }
    }
    action?.let { (p, t) -> RosterDialog(c, clubId, p, t, onDismiss = { action = null }) { action = null; refresh() } }
}

@Composable
private fun RosterDialog(c: JsonObject, clubId: String, p: JsonObject, type: String, onDismiss: () -> Unit, onDone: () -> Unit) {
    val g = graph()
    val ui = LocalUi.current
    val scope = rememberCoroutineScope()
    val squads = c.arr("other_squads")
    var to by remember { mutableStateOf(squads.firstOrNull()?.str("squad_id")) }
    var loanEnd by remember { mutableStateOf(LocalDate.now().plusDays(30).toString()) }
    var reason by remember { mutableStateOf("") }
    var confirm by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    val name = p.str("name") ?: ""
    val toName = squads.firstOrNull { it.str("squad_id") == to }?.str("name") ?: ""
    val verb = when (type) { "transfer" -> "Transfer"; "loan" -> "Loan"; else -> "Release" }
    val loanValid = type != "loan" || (try { LocalDate.parse(loanEnd).isAfter(LocalDate.now()) } catch (e: Exception) { false })

    if (!confirm) AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("$verb $name") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                if (type != "release") {
                    Text("Destination club", style = MaterialTheme.typography.labelSmall, color = extra.muted)
                    if (squads.isEmpty()) Text("There are no other clubs in this league.")
                    squads.forEach { s ->
                        Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).selectable(to == s.str("squad_id"), role = Role.RadioButton) { to = s.str("squad_id") },
                            verticalAlignment = Alignment.CenterVertically) {
                            RadioButton(selected = to == s.str("squad_id"), onClick = null); Text(s.str("name") ?: "", Modifier.padding(start = 8.dp))
                        }
                    }
                }
                if (type == "loan") OutlinedTextField(loanEnd, { loanEnd = it }, label = { Text("Loan ends (YYYY-MM-DD)") }, singleLine = true,
                    isError = !loanValid, supportingText = { if (!loanValid) Text("Enter a future date like 2026-12-31") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(reason, { reason = it }, label = { Text("Reason (optional)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            }
        },
        confirmButton = {
            Button(onClick = { confirm = true }, enabled = (type == "release" || to != null) && loanValid, modifier = Modifier.heightIn(min = 48.dp)) { Text("Continue") }
        },
        dismissButton = { TextButton(onClick = onDismiss, modifier = Modifier.heightIn(min = 48.dp)) { Text("Cancel") } },
    ) else Confirm(
        title = "$verb $name?",
        body = when (type) {
            "transfer" -> "$name will move permanently to $toName from today."
            "loan" -> "$name will play for $toName until $loanEnd, then return automatically."
            else -> "$name will leave ${c.str("name")} today. This is recorded in the roster history."
        },
        confirm = if (busy) "Saving…" else verb, danger = type == "release",
        onDismiss = onDismiss,
    ) {
        if (busy) return@Confirm
        busy = true
        scope.launch {
            val pid = p.str("player_id") ?: ""
            val base = g.repo.cached("/api/v1/players/$pid/history")?.data?.arr("history")?.size ?: 0
            val title = when (type) { "transfer" -> "Transfer $name to $toName"; "loan" -> "Loan $name to $toName"; else -> "Release $name" }
            val out = g.sync.rosterAction(
                clubId = clubId, leagueId = c.str("league_id") ?: "", playerId = pid, type = type,
                toSquadId = if (type == "release") null else to, effectiveDate = SyncManager.today(),
                loanEndDate = if (type == "loan") loanEnd else null, reason = reason.ifBlank { "Club manager action" },
                baseVersion = base, title = title,
            )
            busy = false
            ui.toast(when (out) { is Outcome.Done -> "Done. $title."; else -> out.message })
            if (out is Outcome.Failed) onDismiss() else onDone()
        }
    }
}

@Composable
private fun Info(c: JsonObject) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        val v = c.obj("home_venue")
        SectionLabel("Home venue")
        RowItem {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Icon(Icons.Filled.Place, null, tint = extra.muted)
                Column {
                    Text(v?.str("name") ?: "Not set", fontWeight = FontWeight.Medium)
                    if (v?.dbl("lat") != null) Text("%.4f, %.4f".format(v.dbl("lat"), v.dbl("lng") ?: 0.0), fontSize = 12.sp, color = extra.muted)
                }
            }
        }
        val staff = c.arr("staff")
        SectionLabel("Staff")
        if (staff.isEmpty()) RowItem { Text("No staff listed", color = extra.muted) }
        staff.forEach { s ->
            RowItem { Row { Text(s.str("name") ?: "", Modifier.weight(1f)); Text(Messages.label(s.str("role")), color = extra.muted) } }
            Divider()
        }
        val socials = c.obj("socials")
        if (socials != null && socials.isNotEmpty()) {
            SectionLabel("Social")
            socials.forEach { (k, value) ->
                RowItem { Row { Text(Messages.label(k), Modifier.weight(1f)); Text((value as? JsonPrimitive)?.content ?: "", color = extra.muted) } }
                Divider()
            }
        }
        val history = c["history"]
        val lines = (history as? kotlinx.serialization.json.JsonArray)?.map { el ->
            (el as? JsonPrimitive)?.content ?: (el as? JsonObject)?.let { o -> listOfNotNull(o.str("year") ?: o["year"]?.toString(), o.str("title") ?: o.str("event") ?: o.str("text")).joinToString(" · ") } ?: el.toString()
        } ?: emptyList()
        if (lines.isNotEmpty()) {
            SectionLabel("History")
            lines.forEach { RowItem { Text(it) }; Divider() }
        }
        Box(Modifier.height(24.dp))
    }
}

@Composable
private fun Moves(c: JsonObject) {
    val moves = c.arr("recent_moves")
    if (moves.isEmpty()) {
        Empty(Icons.Filled.Groups, "No moves yet", "Transfers, loans and releases appear here."); return
    }
    LazyColumn(Modifier.fillMaxSize()) {
        items(moves) { m ->
            RowItem {
                Column {
                    Text(Messages.label(m.str("action") ?: m.str("type")) + " · " + (m.str("player_name") ?: m.str("player_id") ?: ""), fontWeight = FontWeight.Medium)
                    Text(listOfNotNull(m.str("effective_date"), m.str("reason")).joinToString(" · "), fontSize = 12.sp, color = extra.muted)
                }
            }
            Divider()
        }
    }
}
