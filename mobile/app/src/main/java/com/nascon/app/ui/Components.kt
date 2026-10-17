package com.nascon.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.CloudOff
import androidx.compose.material.icons.filled.ErrorOutline
import androidx.compose.material.icons.filled.Remove
import androidx.compose.material.icons.filled.Sync
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.nascon.app.data.ApiError
import com.nascon.app.data.Loaded
import com.nascon.app.graph
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

val extra: Extra @Composable get() = LocalExtra.current

@Composable
fun Logo(text: String, size: Int = 28) {
    Box(
        Modifier.size(size.dp).clip(RoundedCornerShape(5.dp)).background(MaterialTheme.colorScheme.primary)
            .semantics { contentDescription = "Club logo" },
        contentAlignment = Alignment.Center,
    ) {
        Text(text, color = Color.White, fontWeight = FontWeight.Bold, fontSize = (size * 0.42).sp)
        Box(Modifier.align(Alignment.BottomCenter).fillMaxWidth().padding(0.dp).heightIn(3.dp, 3.dp).background(extra.gold))
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun Bar(title: String, onBack: (() -> Unit)? = null, logo: String? = null, actions: @Composable () -> Unit = {}) {
    TopAppBar(
        title = {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                if (logo != null && onBack == null) Logo(logo)
                Text(title, maxLines = 1, overflow = TextOverflow.Ellipsis, style = MaterialTheme.typography.titleMedium)
            }
        },
        navigationIcon = {
            if (onBack != null) IconButton(onClick = onBack) {
                Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
            }
        },
        actions = { actions() },
        colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface),
        windowInsets = androidx.compose.foundation.layout.WindowInsets(0, 0, 0, 0),
        expandedHeight = 56.dp,
    )
}

/** Always-visible connection state: Online / Offline / Syncing, with the number of saved actions. */
@Composable
fun NetBar(online: Boolean, syncing: Boolean, pending: Int, savedAt: Long?, onOpenQueue: () -> Unit) {
    val x = extra
    val (bg, fg, text) = when {
        !online -> Triple(x.warnBg, x.warn, buildString {
            append("Offline")
            if (savedAt != null) append(" · showing data saved ${time(savedAt)}")
            if (pending > 0) append(" · $pending saved")
        })
        syncing -> Triple(x.tint, x.link, "Syncing $pending saved action${if (pending == 1) "" else "s"}…")
        pending > 0 -> Triple(x.tint, x.link, "Online · $pending action${if (pending == 1) "" else "s"} waiting to send")
        else -> Triple(MaterialTheme.colorScheme.surface, x.muted, "Online")
    }
    Column {
        Row(
            Modifier.fillMaxWidth().background(bg).clickable(onClickLabel = "Open saved actions") { onOpenQueue() }
                .heightIn(min = 28.dp).padding(horizontal = 16.dp, vertical = 4.dp)
                .semantics(mergeDescendants = true) {},
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            when {
                !online -> Icon(Icons.Filled.CloudOff, null, tint = fg, modifier = Modifier.size(14.dp))
                syncing -> Icon(Icons.Filled.Sync, null, tint = fg, modifier = Modifier.size(14.dp))
                else -> Box(Modifier.size(7.dp).clip(CircleShape).background(if (pending > 0) x.link else x.ok))
            }
            Text(text, color = fg, fontSize = 12.sp, fontWeight = FontWeight.Medium, modifier = Modifier.weight(1f),
                maxLines = 1, overflow = TextOverflow.Ellipsis)
            if (pending > 0 || !online) Text("View", color = fg, fontSize = 12.sp, fontWeight = FontWeight.Bold)
        }
        HorizontalDivider(color = x.line)
    }
}

fun time(ms: Long): String = SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date(ms))

@Composable
fun SectionLabel(text: String, modifier: Modifier = Modifier, trailing: @Composable () -> Unit = {}) {
    Row(modifier.fillMaxWidth().padding(start = 20.dp, end = 12.dp, top = 20.dp, bottom = 8.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Text(text, fontSize = 19.sp, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onBackground, modifier = Modifier.weight(1f))
        trailing()
    }
}

@Composable
fun LiveMark(text: String = "LIVE") {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        Box(Modifier.size(6.dp).clip(CircleShape).background(extra.live))
        Text(text, color = extra.live, fontWeight = FontWeight.Bold, fontSize = 12.sp, letterSpacing = 0.5.sp)
    }
}

enum class Qual { CLINCHED, ELIMINATED, POSSIBLE }

fun qualOf(s: String?) = when (s) {
    "clinched" -> Qual.CLINCHED
    "eliminated" -> Qual.ELIMINATED
    else -> Qual.POSSIBLE
}

fun qualLabel(q: Qual) = when (q) {
    Qual.CLINCHED -> "Clinched"
    Qual.ELIMINATED -> "Eliminated"
    Qual.POSSIBLE -> "Still possible"
}

@Composable
fun QualIcon(q: Qual, size: Int = 20) {
    val x = extra
    val (bg, fg, icon) = when (q) {
        Qual.CLINCHED -> Triple(x.okBg, x.ok, Icons.Filled.Check)
        Qual.ELIMINATED -> Triple(x.badBg, x.bad, Icons.Filled.Close)
        Qual.POSSIBLE -> Triple(MaterialTheme.colorScheme.surfaceVariant, x.muted, Icons.Filled.Remove)
    }
    Box(Modifier.size(size.dp).clip(CircleShape).background(bg), contentAlignment = Alignment.Center) {
        Icon(icon, contentDescription = qualLabel(q), tint = fg, modifier = Modifier.size((size * 0.62).dp))
    }
}

@Composable
fun Chip(text: String, fg: Color, bg: Color, icon: ImageVector? = null) {
    Row(
        Modifier.clip(RoundedCornerShape(4.dp)).background(bg).padding(horizontal = 8.dp, vertical = 3.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        if (icon != null) Icon(icon, null, tint = fg, modifier = Modifier.size(12.dp))
        Text(text, color = fg, fontSize = 11.sp, fontWeight = FontWeight.Medium)
    }
}

@Composable
fun Crest(name: String, size: Int = 24) {
    val initials = name.split(" ").filter { it.isNotBlank() }.take(2).joinToString("") { it.take(1).uppercase() }
    Box(
        Modifier.size(size.dp).clip(CircleShape).background(MaterialTheme.colorScheme.surfaceVariant),
        contentAlignment = Alignment.Center,
    ) { Text(initials, fontSize = (size * 0.36).sp, fontWeight = FontWeight.Bold, color = extra.muted) }
}

@Composable
fun Empty(icon: ImageVector, title: String, body: String, action: (@Composable () -> Unit)? = null) {
    Column(
        Modifier.fillMaxWidth().padding(horizontal = 32.dp, vertical = 48.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Icon(icon, null, tint = extra.muted, modifier = Modifier.size(36.dp))
        Text(title, style = MaterialTheme.typography.titleMedium, textAlign = TextAlign.Center)
        Text(body, color = extra.muted, textAlign = TextAlign.Center, style = MaterialTheme.typography.bodyMedium)
        if (action != null) {
            Spacer(Modifier.size(8.dp)); action()
        }
    }
}

@Composable
fun Loading() {
    Box(Modifier.fillMaxWidth().padding(48.dp), contentAlignment = Alignment.Center) {
        CircularProgressIndicator(Modifier.semantics { contentDescription = "Loading" })
    }
}

@Composable
fun ErrorState(message: String, onRetry: () -> Unit) {
    Empty(Icons.Filled.ErrorOutline, "Couldn't load this", message) {
        OutlinedButton(onClick = onRetry, modifier = Modifier.heightIn(min = 48.dp)) { Text("Try again") }
    }
}

@Composable
fun Confirm(
    title: String, body: String, confirm: String, danger: Boolean = false,
    onDismiss: () -> Unit, onConfirm: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = { Text(body) },
        confirmButton = {
            Button(
                onClick = onConfirm,
                colors = if (danger) ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error,
                    contentColor = MaterialTheme.colorScheme.onError) else ButtonDefaults.buttonColors(),
                modifier = Modifier.heightIn(min = 48.dp),
            ) { Text(confirm) }
        },
        dismissButton = { TextButton(onClick = onDismiss, modifier = Modifier.heightIn(min = 48.dp)) { Text("Cancel") } },
    )
}

/** Loads one API path through the cache-backed repo. Re-runs when [key] or the reload counter changes. */
class Res(val loaded: Loaded?, val error: String?, val loading: Boolean, val reload: () -> Unit)

@Composable
fun rememberRes(path: String?, vararg keys: Any?): Res {
    val g = graph()
    var tick by remember { mutableIntStateOf(0) }
    var loaded by remember(path) { mutableStateOf<Loaded?>(null) }
    var error by remember(path) { mutableStateOf<String?>(null) }
    var loading by remember(path) { mutableStateOf(true) }
    LaunchedEffect(path, tick, *keys) {
        if (path == null) return@LaunchedEffect
        loading = true
        if (loaded == null) loaded = g.repo.cached(path)
        try {
            loaded = g.repo.load(path); error = null
        } catch (e: ApiError) {
            if (loaded == null) error = e.message
        } finally {
            loading = false
        }
    }
    return Res(loaded, error, loading) { tick++ }
}

@Composable
fun ResBox(res: Res, content: @Composable (Loaded) -> Unit) {
    val l = res.loaded
    when {
        l != null -> content(l)
        res.error != null -> ErrorState(res.error, res.reload)
        else -> Loading()
    }
}

val Gutter = PaddingValues(horizontal = 16.dp)

@Composable
fun Divider() = HorizontalDivider(color = extra.line)

@Composable
fun RowItem(modifier: Modifier = Modifier, onClick: (() -> Unit)? = null, content: @Composable () -> Unit) {
    Box(
        modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface)
            .let { if (onClick != null) it.clickable(onClick = onClick) else it }
            .heightIn(min = 48.dp).padding(horizontal = 16.dp, vertical = 8.dp),
        contentAlignment = Alignment.CenterStart,
    ) { content() }
}

@Composable
fun Spacer8() = Spacer(Modifier.size(8.dp))

@Composable
fun W(dp: Int) = Spacer(Modifier.width(dp.dp))
