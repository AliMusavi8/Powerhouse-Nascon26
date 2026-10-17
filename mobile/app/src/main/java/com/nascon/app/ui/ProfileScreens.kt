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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ReceiptLong
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.CloudDone
import androidx.compose.material.icons.filled.ErrorOutline
import androidx.compose.material.icons.filled.HourglassTop
import androidx.compose.material.icons.filled.Sports
import androidx.compose.material.icons.filled.SwapHoriz
import androidx.compose.material.icons.filled.Sync
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.nascon.app.data.PendingAction
import com.nascon.app.graph
import kotlinx.coroutines.launch

@Composable
fun ProfileScreen() {
    val g = graph()
    val ui = LocalUi.current
    val u = ui.session.user
    var confirmOut by remember { mutableStateOf(false) }
    val pending by g.db.actions().observePendingCount().collectAsStateWithLifecycle(0)
    Page("Profile") {
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
            Row(Modifier.fillMaxWidth().cardRow().padding(16.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                Crest(u.name, 48)
                Column {
                    Text(u.name, style = MaterialTheme.typography.titleMedium)
                    Text(u.email, color = extra.muted, fontSize = 13.sp)
                    Text("${u.roleLabel} · ${ui.session.branding.name}", color = extra.muted, fontSize = 13.sp)
                }
            }
            SectionLabel("What you can do")
            Column(Modifier.cardRow()) {
                Line("View fixtures, standings and clubs", true)
                Line("Buy from the club store", true)
                Line("Enter match scores", ui.session.canScore)
                Line("Manage the club roster", ui.session.canManage)
            }
            SectionLabel("Activity")
            RowItem(onClick = { ui.nav.navigate("queue") }) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Icon(Icons.Filled.Sync, null, tint = extra.muted)
                    Text("Saved actions", Modifier.weight(1f))
                    Text(if (pending == 0) "None waiting" else "$pending waiting", color = extra.muted, fontSize = 13.sp)
                }
            }
            Divider()
            RowItem(onClick = { ui.nav.navigate("orders") }) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Icon(Icons.AutoMirrored.Filled.ReceiptLong, null, tint = extra.muted)
                    Text("Orders and receipts", Modifier.weight(1f))
                }
            }
            SectionLabel("Server")
            RowItem { Text(g.settings.serverUrl, color = extra.muted) }
            Box(Modifier.padding(16.dp)) {
                OutlinedButton(onClick = { confirmOut = true }, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)) {
                    Icon(Icons.AutoMirrored.Filled.Logout, null); Text("  Sign out")
                }
            }
        }
    }
    if (confirmOut) Confirm(
        "Sign out?",
        if (pending > 0) "You have $pending saved action${if (pending == 1) "" else "s"}. They stay on this phone and send when you're back online."
        else "You can sign back in at any time.",
        "Sign out", onDismiss = { confirmOut = false },
    ) { confirmOut = false; g.session.signOut() }
}

@Composable
private fun Line(text: String, yes: Boolean) {
    Row(Modifier.fillMaxWidth().heightIn(min = 44.dp).padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Icon(if (yes) Icons.Filled.CheckCircle else Icons.Filled.ErrorOutline, contentDescription = if (yes) "Allowed" else "Not allowed",
            tint = if (yes) extra.ok else extra.muted, modifier = Modifier.size(18.dp))
        Text(text, color = if (yes) MaterialTheme.colorScheme.onSurface else extra.muted)
    }
}

@Composable
fun QueueScreen() {
    val g = graph()
    val ui = LocalUi.current
    val scope = rememberCoroutineScope()
    val all by g.db.actions().observeAll().collectAsStateWithLifecycle(emptyList())
    val online by g.network.online.collectAsStateWithLifecycle()
    val syncing by g.sync.syncing.collectAsStateWithLifecycle()
    val pending = all.filter { it.state == PendingAction.STATE_PENDING }
    val done = all.filter { it.state != PendingAction.STATE_PENDING }.sortedByDescending { it.resolvedAt ?: 0 }
    Page("Saved actions", back = true) {
        LazyColumn(Modifier.fillMaxSize()) {
            item {
                Column(Modifier.fillMaxWidth().cardRow().padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(
                        when {
                            pending.isEmpty() -> "Nothing waiting to send."
                            !online -> "${pending.size} action${if (pending.size == 1) "" else "s"} saved on this phone. They send automatically when you reconnect."
                            else -> "${pending.size} action${if (pending.size == 1) "" else "s"} ready to send."
                        },
                    )
                    Button(
                        onClick = {
                            if (!online) ui.toast("You're still offline. Actions will send when you reconnect.")
                            else scope.launch { g.sync.syncNow() }
                        },
                        enabled = pending.isNotEmpty() && !syncing,
                        modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                    ) { Icon(Icons.Filled.Sync, null); Text(if (syncing) "  Syncing…" else "  Sync now") }
                }
                Divider()
            }
            if (pending.isNotEmpty()) {
                item { SectionLabel("Pending") }
                items(pending, key = { it.actionId }) { ActionRow(it) }
            }
            if (done.isNotEmpty()) {
                item {
                    SectionLabel("Results") {
                        TextButton(onClick = { scope.launch { g.db.actions().clearResolved() } }, modifier = Modifier.heightIn(min = 48.dp)) { Text("Clear") }
                    }
                }
                items(done, key = { it.actionId }) { ActionRow(it) }
            }
            if (all.isEmpty()) item {
                Empty(Icons.Filled.CloudDone, "No pending actions", "Scores and roster changes you make offline appear here until they're sent.")
            }
        }
    }
}

@Composable
private fun ActionRow(a: PendingAction) {
    val x = extra
    val (icon, color, text) = when (a.state) {
        PendingAction.STATE_PENDING -> Triple(Icons.Filled.HourglassTop, x.warn, "Pending · waiting to send")
        PendingAction.STATE_APPLIED -> Triple(Icons.Filled.CheckCircle, x.ok, a.result ?: "Applied.")
        PendingAction.STATE_DUPLICATE -> Triple(Icons.Filled.CheckCircle, x.muted, a.result ?: "Already recorded.")
        else -> Triple(Icons.Filled.ErrorOutline, x.bad, a.result ?: "Not applied.")
    }
    Column(Modifier.fillMaxWidth().cardRow()) {
        Row(Modifier.padding(horizontal = 16.dp, vertical = 12.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Box(Modifier.size(36.dp).clip(RoundedCornerShape(8.dp)).background(MaterialTheme.colorScheme.surfaceVariant), contentAlignment = Alignment.Center) {
                Icon(if (a.type == "score_event") Icons.Filled.Sports else Icons.Filled.SwapHoriz,
                    contentDescription = if (a.type == "score_event") "Score action" else "Roster action", tint = x.muted)
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(a.title, fontWeight = FontWeight.Medium)
                Text("Saved at ${time(a.createdAt)} · ${a.owner}", fontSize = 12.sp, color = x.muted)
                Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.padding(top = 4.dp)) {
                    Icon(icon, null, tint = color, modifier = Modifier.size(16.dp))
                    Text(text, color = color, fontSize = 13.sp)
                }
            }
        }
        Divider()
        Box(Modifier.height(0.dp))
    }
}
