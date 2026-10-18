package com.nascon.app.ui

import android.net.Uri
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import com.nascon.app.data.Api
import com.nascon.app.data.ApiError
import com.nascon.app.data.bool
import com.nascon.app.data.int
import com.nascon.app.data.obj
import com.nascon.app.data.str
import com.nascon.app.graph
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

// ---------------------------------------------------------------- native QR scanner (FR-4.1)

/** Resolve a scanned code: nascon:// links directly, /q/<code> short links through the server's live routing. */
suspend fun resolveScan(api: Api, text: String): DeepLink? {
    val uri = Uri.parse(text.trim())
    DeepLink.parse(uri)?.let { return it }
    val segs = uri.pathSegments
    if (segs.size >= 2 && segs[segs.size - 2] == "q") {
        val v = api.get("/q/${segs.last()}?format=json", auth = "")
        val id = v.str("entity_id") ?: return null
        return if (v.str("entity_type") == "costream") DeepLink("stream", id) else DeepLink("entity", id)
    }
    return null
}

@Composable
fun rememberQrScanner(onLink: (DeepLink) -> Unit): () -> Unit {
    val g = graph()
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val launcher = rememberLauncherForActivityResult(ScanContract()) { result ->
        val text = result.contents ?: return@rememberLauncherForActivityResult
        scope.launch {
            val link = try { resolveScan(g.api, text) } catch (e: ApiError) { null }
            if (link != null) onLink(link) else Toast.makeText(ctx, "That QR code is not a Scorix link.", Toast.LENGTH_LONG).show()
        }
    }
    return {
        launcher.launch(ScanOptions().setDesiredBarcodeFormats(ScanOptions.QR_CODE).setPrompt("Scan a Scorix QR code")
            .setBeepEnabled(false).setOrientationLocked(true))
    }
}

// ---------------------------------------------------------------- athlete profile from a QR / deep link (FR-3.1)

@Composable
fun AthleteLive(playerId: String, onClose: () -> Unit) {
    val g = graph()
    val scope = rememberCoroutineScope()
    var p by remember { mutableStateOf<JsonObject?>(null) }
    var note by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(playerId) {
        try { p = g.api.get("/api/v1/players/$playerId/profile") } catch (e: ApiError) { note = e.message }
    }
    Column(Modifier.fillMaxSize().testTag("athlete-screen")) {
        Bar("Athlete", onBack = onClose)
        Column(Modifier.padding(16.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            val d = p
            Text(d?.str("name") ?: playerId, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            val club = (d?.get("affiliations") as? kotlinx.serialization.json.JsonArray)?.firstOrNull() as? JsonObject
            club?.str("name")?.let { Text("Plays for $it") }
            d?.obj("career")?.let { c ->
                Text("Career: ${c.int("played")} played · ${c.int("won")} won · ${c.int("drawn")} drawn · ${c.int("lost")} lost")
            }
            Text("${d?.int("follower_count") ?: 0} followers", fontWeight = FontWeight.Bold)
            val following = d?.bool("following") == true
            Button(onClick = {
                scope.launch {
                    try {
                        val r = if (following) g.api.delete("/api/v1/players/$playerId/follow")
                        else g.api.post("/api/v1/players/$playerId/follow", buildJsonObject { })
                        p = d?.let { JsonObject(it + mapOf("following" to kotlinx.serialization.json.JsonPrimitive(r.bool("following")),
                            "follower_count" to kotlinx.serialization.json.JsonPrimitive(r.int("follower_count")))) }
                        note = null
                    } catch (e: ApiError) { note = if (e.status == 401 || e.status == 403) "Sign in to follow athletes." else e.message }
                }
            }, modifier = Modifier.heightIn(min = 48.dp).testTag("follow-button")) { Text(if (following) "Following" else "Follow") }
            note?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        }
    }
}

// ---------------------------------------------------------------- broadcaster tools (FR-3.2)

@Composable
fun BroadcastScreen(onBack: () -> Unit) {
    val g = graph()
    val scope = rememberCoroutineScope()
    var key by remember { mutableStateOf<JsonObject?>(null) }
    var note by remember { mutableStateOf<String?>(null) }
    val host = Uri.parse(g.api.base()).host ?: "localhost"
    fun local(url: String?) = url?.replace("//localhost:", "//$host:")
    fun act(action: String) = scope.launch {
        try { key = g.api.post("/api/v1/streams/key", buildJsonObject { put("action", action); put("label", "Scorix app") }); note = null }
        catch (e: ApiError) { note = e.message }
    }
    LaunchedEffect(Unit) { act("generate") }

    Column(Modifier.fillMaxSize().testTag("broadcast-screen")) {
        Bar("Go live", onBack = onBack)
        Column(Modifier.padding(16.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            val k = key
            val active = k?.str("status") == "active"
            Text(if (active) "Your stream key is active. Point OBS or FFmpeg at the RTMP address, or use WHIP for low latency."
                 else "Your stream key is revoked. Create a new one to go live.")
            Surface(shape = RoundedCornerShape(16.dp), tonalElevation = 2.dp, modifier = Modifier.fillMaxWidth()) {
                SelectionContainer {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text("Stream key", style = MaterialTheme.typography.labelLarge)
                        Text(k?.str("stream_key") ?: "…", fontFamily = FontFamily.Monospace)
                        if (active) {
                            Text("RTMP", style = MaterialTheme.typography.labelLarge)
                            Text(local(k?.obj("ingest_endpoints")?.str("rtmp")) ?: "", fontFamily = FontFamily.Monospace)
                            Text("WebRTC (WHIP)", style = MaterialTheme.typography.labelLarge)
                            Text(local(k?.obj("ingest_endpoints")?.str("webrtc")) ?: "", fontFamily = FontFamily.Monospace)
                        }
                    }
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { act(if (active) "rotate" else "generate") }, modifier = Modifier.heightIn(min = 48.dp)) {
                    Text(if (active) "Rotate key" else "New key")
                }
                if (active) OutlinedButton(onClick = { act("revoke") }, modifier = Modifier.heightIn(min = 48.dp)) { Text("Revoke") }
            }
            if (active) {
                Text("Live preview", style = MaterialTheme.typography.titleMedium)
                LivePreview(local(k?.str("playback_url")))
            }
            note?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        }
    }
}
