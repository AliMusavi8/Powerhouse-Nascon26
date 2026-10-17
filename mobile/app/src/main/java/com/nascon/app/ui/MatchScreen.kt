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

    val m = res.loaded?.data
    val title = m?.let { "${it.obj("home")?.str("name")} v ${it.obj("away")?.str("name")}" } ?: "Match"
    Page(title, back = true, savedAt = res.loaded?.savedAt) {
        ResBox(res) { l ->
            val d = l.data
            val canScore = d.bool("can_score") && ui.session.canScore
            Column(Modifier.fillMaxSize()) {
                LazyColumn(Modifier.weight(1f)) {
                    item { ScoreHeader(d, liveConnected && !l.fromCache) }
                    d.obj("pinned_product")?.let { p -> item { PinnedProduct(p) { ui.nav.navigate("product/${p.str("product_id")}") } } }
                    item { SectionLabel("Timeline") }
                    val events = d.arr("events").reversed()
                    if (events.isEmpty()) item {
                        Empty(Icons.Filled.Timeline, "No events yet", if (d.str("status") == "upcoming") "The match hasn't started." else "Events appear here as they happen.")
                    }
                    items(events, key = { it.str("event_id") ?: it.int("sequence").toString() }) { EventRow(it, d) }
                    item { Box(Modifier.height(16.dp)) }
                }
                if (canScore) OrganiserBar(matchId, d) { res.reload() }
            }
        }
    }
}

private fun teamName(d: JsonObject, teamId: String?): String = when (teamId) {
    d.obj("home")?.str("team_id") -> d.obj("home")?.str("name") ?: "Home"
    d.obj("away")?.str("team_id") -> d.obj("away")?.str("name") ?: "Away"
    else -> teamId ?: ""
}

@Composable
private fun ScoreHeader(d: JsonObject, live: Boolean) {
    val home = d.obj("home")
    val away = d.obj("away")
    val status = d.str("status")
    fun scoreText(s: JsonObject?) = buildString {
        append(s?.int("score") ?: 0)
        s?.int("wickets")?.let { append("/$it") }
    }
    val desc = "${home?.str("name")} ${scoreText(home)}, ${away?.str("name")} ${scoreText(away)}. " + statusText(status, d)
    Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface).padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(Modifier.fillMaxWidth().semantics(mergeDescendants = true) { contentDescription = desc }, verticalAlignment = Alignment.CenterVertically) {
            TeamCol(home, Modifier.weight(1f))
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(scoreText(home), style = ScoreStyle)
                    Text("–", style = ScoreStyle, color = extra.muted, fontWeight = FontWeight.Light)
                    Text(scoreText(away), style = ScoreStyle)
                }
                if (home?.str("overs") != null) Text("${home.str("overs")} ov  ·  ${away?.str("overs")} ov", fontSize = 12.sp, color = extra.muted)
            }
            TeamCol(away, Modifier.weight(1f))
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            when (status) {
                "in_progress" -> LiveMark()
                "completed" -> Chip("Full time", extra.muted, MaterialTheme.colorScheme.surfaceVariant, Icons.Filled.Flag)
                else -> Chip("Upcoming", extra.muted, MaterialTheme.colorScheme.surfaceVariant)
            }
            val info = listOfNotNull(d.str("venue"), parseTime(d.str("scheduled_at"))?.let { "${dayLabel(it)} ${clock(it)}" }).joinToString(" · ")
            if (info.isNotBlank()) Text(info, fontSize = 12.sp, color = extra.muted)
        }
        if (status == "completed") Text(statusText(status, d), fontSize = 13.sp, color = extra.muted)
        if (status == "in_progress") Text(if (live) "Live updates on" else "Live updates paused · reconnecting", fontSize = 11.sp, color = extra.muted)
    }
    Divider()
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
private fun TeamCol(t: JsonObject?, modifier: Modifier) {
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Crest(t?.str("name") ?: "", 40)
        Text(t?.str("name") ?: "", textAlign = TextAlign.Center, maxLines = 2, overflow = TextOverflow.Ellipsis, fontSize = 13.sp, fontWeight = FontWeight.Medium)
    }
}

@Composable
private fun PinnedProduct(p: JsonObject, onBuy: () -> Unit) {
    val v = p.arr("variants").firstOrNull()
    SectionLabel("Pinned by the club")
    Row(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface).clickable(onClickLabel = "Open product", onClick = onBuy)
        .padding(horizontal = 16.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Box(Modifier.size(48.dp).clip(RoundedCornerShape(8.dp)).background(MaterialTheme.colorScheme.surfaceVariant), contentAlignment = Alignment.Center) {
            Icon(Icons.Filled.ShoppingBag, null, tint = extra.muted)
        }
        Column(Modifier.weight(1f)) {
            Text(p.str("name") ?: "", fontWeight = FontWeight.Medium, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(money(v?.long("price_minor"), v?.str("currency")), style = NumStyle, color = extra.muted)
        }
        Button(onClick = onBuy, modifier = Modifier.heightIn(min = 48.dp)) { Text("Buy") }
    }
    Divider()
}

@Composable
private fun EventRow(e: JsonObject, d: JsonObject) {
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
    Column(Modifier.background(MaterialTheme.colorScheme.surface)) {
        Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).padding(horizontal = 16.dp, vertical = 8.dp),
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
        Divider()
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
        Divider()
        Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Organiser", fontSize = 12.sp, color = extra.muted, modifier = Modifier.weight(1f))
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
