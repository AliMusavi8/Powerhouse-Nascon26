package com.nascon.app.ui

import android.net.Uri
import android.widget.VideoView
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import com.nascon.app.data.long
import com.nascon.app.data.money
import androidx.compose.ui.graphics.Color
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import com.nascon.app.data.ApiError
import com.nascon.app.data.arr
import com.nascon.app.data.int
import com.nascon.app.data.json
import com.nascon.app.data.obj
import com.nascon.app.data.str
import com.nascon.app.graph
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener

/** A parsed nascon:// link: nascon://entity/{id} or nascon://stream/{cs-session-id}. */
data class DeepLink(val kind: String, val id: String) {
    val isCostream get() = kind == "stream" || id.startsWith("cs-session-")

    companion object {
        fun parse(uri: Uri?): DeepLink? {
            if (uri == null || uri.scheme != "nascon") return null
            val id = uri.pathSegments.firstOrNull() ?: return null
            return when (uri.host) {
                "entity", "stream" -> DeepLink(uri.host!!, id)
                else -> null
            }
        }
    }
}

/**
 * Deep-link landing screen. Works signed in or not: match and co-stream data come from the read-only guest API,
 * so a QR scan or `adb am start nascon://...` never stops on the login screen (spec 6.3).
 */
@Composable
fun DeepLinkScreen(link: DeepLink, onClose: () -> Unit) {
    when {
        link.isCostream -> CoStreamLive(link.id, onClose)
        link.id.startsWith("player-") -> AthleteLive(link.id, onClose)
        else -> MatchLive(link.id, onClose)
    }
}

@Composable
fun LivePreview(url: String?) = LiveVideo(url, "Live preview of your stream")

private fun mediaUrl(base: String, url: String?): String? {
    // Media URLs are issued for localhost; point them at the host the app talks to (emulator, USB or LAN).
    val host = Uri.parse(base).host ?: return url
    return url?.replace("//localhost:", "//$host:")
}

/** Same frame as the app's Page: striped brand header with a hero slot, then the warm rounded sheet. */
@Composable
fun LivePage(title: String, onBack: () -> Unit, hero: @Composable () -> Unit, content: @Composable ColumnScope.() -> Unit) {
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.primary)) {
        Box {
            Stripes(Modifier.matchParentSize())
            Column(Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 20.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    CircleButton(androidx.compose.material.icons.Icons.AutoMirrored.Filled.ArrowBack, "Back", onBack)
                    Text(title, color = Color.White, fontSize = 16.sp, fontWeight = FontWeight.Medium, modifier = Modifier.weight(1f))
                    BadgePill("Live", dot = true)
                }
                Box(Modifier.padding(top = 16.dp)) { hero() }
            }
        }
        Column(
            Modifier.fillMaxSize().clip(RoundedCornerShape(topStart = 28.dp, topEnd = 28.dp))
                .background(MaterialTheme.colorScheme.background)
        ) { content() }
    }
}

@Composable
private fun LiveVideo(url: String?, label: String) {
    Box(
        Modifier.fillMaxWidth().aspectRatio(16f / 9f).clip(RoundedCornerShape(20.dp)).background(Color.Black)
            .semantics { contentDescription = label }.testTag("live-video"),
        contentAlignment = Alignment.Center
    ) {
        if (url != null) {
            AndroidView(factory = { ctx ->
                VideoView(ctx).apply {
                    setOnPreparedListener { it.isLooping = true; it.setVolume(0f, 0f); start() }
                    setOnErrorListener { _, _, _ -> true }
                    setVideoURI(Uri.parse(url))
                }
            }, modifier = Modifier.fillMaxSize())
        } else {
            Text("Connecting to the stream…", color = Color.White.copy(alpha = 0.8f))
        }
    }
}

/** Live socket that re-connects while the screen is open. */
@Composable
private fun LiveSocket(path: String, onMessage: (JsonObject) -> Unit) {
    val g = graph()
    DisposableEffect(path) {
        var closed = false
        var socket: WebSocket? = null
        val handler = android.os.Handler(android.os.Looper.getMainLooper())
        fun connect() {
            if (closed) return
            val url = g.api.base().replaceFirst("http", "ws") + path
            socket = g.api.client.newWebSocket(Request.Builder().url(url).build(), object : WebSocketListener() {
                override fun onMessage(webSocket: WebSocket, text: String) {
                    val msg = try { json.parseToJsonElement(text).jsonObject } catch (e: Exception) { null }
                    if (msg != null) handler.post { onMessage(msg) }
                }
                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    handler.postDelayed({ connect() }, 3000)
                }
            })
        }
        connect()
        onDispose { closed = true; handler.removeCallbacksAndMessages(null); socket?.close(1000, null) }
    }
}

private fun statusText(s: String?) = when (s) {
    "in_progress" -> "In progress"
    "upcoming" -> "Starts soon"
    "completed" -> "Full time"
    null -> "Connecting…"
    else -> s.replaceFirstChar { it.uppercase() }
}

@Composable
private fun MatchLive(matchId: String, onClose: () -> Unit) {
    val g = graph()
    var data by remember { mutableStateOf<JsonObject?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var home by remember { mutableStateOf<Int?>(null) }
    var away by remember { mutableStateOf<Int?>(null) }
    var status by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(matchId) {
        try {
            val d = g.api.get("/api/v1/guest/matches/$matchId", auth = "")
            data = d; home = d.obj("home")?.int("score"); away = d.obj("away")?.int("score"); status = d.str("status")
        } catch (e: ApiError) { error = e.message }
    }
    LiveSocket("/ws/matches/$matchId") { m ->
        if (m.str("type") == "match_updated") {
            m.obj("home")?.int("score")?.let { home = it }
            m.obj("away")?.int("score")?.let { away = it }
            m.str("status")?.let { status = it }
        }
    }

    Box(Modifier.fillMaxSize().testTag("match-live-screen").semantics { contentDescription = "Match live screen" }) {
        val d = data
        LivePage("Match Live", onClose, hero = {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                TeamBlock(d?.obj("home")?.str("name") ?: "Home", Modifier.weight(1f), crest = 64, color = Color.White)
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(if (home != null && away != null) "$home-$away" else "–", color = Color.White, fontSize = 44.sp,
                        fontWeight = FontWeight.ExtraBold,
                        modifier = Modifier.testTag("live-score").semantics { liveRegion = LiveRegionMode.Polite })
                    Text(statusText(status), color = Color.White.copy(alpha = 0.85f), fontSize = 14.sp)
                    d?.str("venue")?.let { Text(it, color = Color.White.copy(alpha = 0.7f), fontSize = 13.sp) }
                }
                TeamBlock(d?.obj("away")?.str("name") ?: "Away", Modifier.weight(1f), crest = 64, color = Color.White)
            }
        }) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                LiveVideo(mediaUrl(g.api.base(), d?.obj("playback")?.str("hls")), "Live match video")
                d?.obj("pinned_product")?.let { p ->
                    val v = (p["variants"] as? kotlinx.serialization.json.JsonArray)?.firstOrNull() as? JsonObject
                    Surface(shape = RoundedCornerShape(22.dp), color = MaterialTheme.colorScheme.surface,
                        border = androidx.compose.foundation.BorderStroke(1.dp, extra.line), modifier = Modifier.fillMaxWidth()) {
                        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text("Pinned by the club", style = MaterialTheme.typography.labelMedium, color = extra.muted)
                                Text(p.str("name") ?: "", fontWeight = FontWeight.Bold, maxLines = 1)
                                v?.long("price_minor")?.let { Text(money(it), color = extra.muted) }
                            }
                        }
                    }
                }
                error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
            ChatPanel("chat-$matchId", Modifier.weight(1f))
        }
    }
}

@Composable
private fun CoStreamLive(sessionId: String, onClose: () -> Unit) {
    val g = graph()
    var data by remember { mutableStateOf<JsonObject?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(sessionId) {
        try { data = g.api.get("/api/v1/guest/costream/$sessionId", auth = "") } catch (e: ApiError) { error = e.message }
    }
    LiveSocket("/ws/costream/$sessionId") { m -> if (m.str("type") == "costream_updated") data = m }

    Box(Modifier.fillMaxSize().testTag("costream-screen").semantics { contentDescription = "Co-stream screen" }) {
        val d = data
        val names = d?.obj("names")
        val host = d?.str("active_host")
        val ended = d?.str("status") == "terminated"
        LivePage("Co-Stream", onClose, hero = {
            Column {
                Text(if (ended) "This co-stream has ended" else (names?.str(host ?: "") ?: host ?: "…"),
                    color = Color.White, fontSize = 26.sp, fontWeight = FontWeight.Bold)
                Text(if (ended) "Thanks for watching" else "Hosting · ${d?.int("participant_count") ?: 0} live · ${(d?.str("layout") ?: "").replace('_', ' ')}",
                    color = Color.White.copy(alpha = 0.85f), fontSize = 14.sp)
            }
        }) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                LiveVideo(mediaUrl(g.api.base(), d?.obj("playback")?.str("hls")
                    ?: "${g.api.base().replace(":8080", ":8888")}/costream/$sessionId/index.m3u8"), "Co-stream video")
                val parts = (d?.get("active_participants") as? kotlinx.serialization.json.JsonArray)
                    ?.mapNotNull { (it as? kotlinx.serialization.json.JsonPrimitive)?.content } ?: emptyList()
                if (parts.isNotEmpty()) Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    parts.forEach { pid ->
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            ClubBadge(names?.str(pid) ?: pid, 44)
                            Text((names?.str(pid) ?: pid).substringBefore(" "), fontSize = 12.sp,
                                fontWeight = if (pid == host) FontWeight.Bold else FontWeight.Normal)
                        }
                    }
                }
                error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
            ChatPanel("chat-$sessionId", Modifier.weight(1f))
        }
    }
}

/** Unified chat (FR-3.3): ordered by server sequence numbers, live over WebSocket. Posting needs a member account. */
@Composable
private fun ChatPanel(room: String, modifier: Modifier) {
    val g = graph()
    val scope = rememberCoroutineScope()
    val messages = remember(room) { mutableStateListOf<JsonObject>() }
    var text by remember { mutableStateOf("") }
    var note by remember { mutableStateOf<String?>(null) }
    val listState = rememberLazyListState()

    fun add(m: JsonObject) {
        val seq = m.int("seq") ?: return
        if (messages.none { it.int("seq") == seq }) {
            messages.add(m); messages.sortBy { it.int("seq") ?: 0 }
        }
    }
    LaunchedEffect(room) {
        try { g.api.get("/api/v1/guest/chat/$room", auth = "").arr("messages").forEach { add(it) } }
        catch (e: ApiError) { /* history is optional */ }
    }
    LiveSocket("/ws/chat/$room") { m -> if (m.str("type") == "chat") add(m) }
    LaunchedEffect(messages.size) { if (messages.isNotEmpty()) listState.animateScrollToItem(messages.size - 1) }

    Surface(
        modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, bottom = 12.dp).testTag("chat-panel"),
        shape = RoundedCornerShape(22.dp), color = MaterialTheme.colorScheme.surface,
        border = androidx.compose.foundation.BorderStroke(1.dp, extra.line)
    ) {
        Column(Modifier.padding(14.dp)) {
            Text("Live chat", fontWeight = FontWeight.Bold, fontSize = 16.sp)
            LazyColumn(Modifier.weight(1f).fillMaxWidth().padding(vertical = 6.dp), state = listState,
                verticalArrangement = Arrangement.spacedBy(6.dp)) {
                if (messages.isEmpty()) item { Text("No messages yet. Say hello!", color = extra.muted) }
                items(messages, key = { it.int("seq") ?: 0 }) { m ->
                    Surface(shape = RoundedCornerShape(14.dp), color = MaterialTheme.colorScheme.background) {
                        Text(buildAnnotated(m.str("sender") ?: "fan", m.str("text") ?: ""),
                            Modifier.padding(horizontal = 12.dp, vertical = 8.dp).testTag("chat-message"))
                    }
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(text, { text = it }, Modifier.weight(1f).heightIn(min = 48.dp),
                    placeholder = { Text("Say something") }, singleLine = true, shape = RoundedCornerShape(24.dp))
                Button(onClick = {
                    val body = buildJsonObject { put("chat_room_id", room); put("text", text) }
                    scope.launch {
                        try { add(g.api.post("/api/v1/chat", body)); text = ""; note = null }
                        catch (e: ApiError) { note = if (e.status == 403 || e.status == 401) "Sign in to join the chat." else e.message }
                    }
                }, modifier = Modifier.padding(start = 8.dp).heightIn(min = 48.dp)) { Text("Send") }
            }
            note?.let { Text(it, color = MaterialTheme.colorScheme.error, fontSize = 13.sp) }
        }
    }
}

private fun buildAnnotated(sender: String, text: String) = androidx.compose.ui.text.buildAnnotatedString {
    pushStyle(androidx.compose.ui.text.SpanStyle(fontWeight = FontWeight.Bold)); append("$sender  "); pop(); append(text)
}
