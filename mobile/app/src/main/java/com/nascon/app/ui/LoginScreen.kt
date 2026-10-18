package com.nascon.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Dns
import androidx.compose.material.icons.filled.ErrorOutline
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Mail
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
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
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.horizontalScroll
import androidx.compose.runtime.LaunchedEffect
import com.nascon.app.data.arr
import com.nascon.app.data.str
import com.nascon.app.data.ApiError
import com.nascon.app.data.jobj
import com.nascon.app.graph
import kotlinx.coroutines.launch

private val demo = listOf(
    "organizer@nascon.test" to "League organiser",
    "manager@nascon.test" to "Club manager",
    "player@nascon.test" to "Player",
    "viewer@nascon.test" to "Viewer",
    "admin@nascon.test" to "Platform admin",
)

@Composable
fun LoginScreen() {
    val g = graph()
    val scope = rememberCoroutineScope()
    var email by remember { mutableStateOf(g.settings.lastEmail) }
    var password by remember { mutableStateOf("") }
    var server by remember { mutableStateOf(g.settings.serverUrl) }
    var showServer by remember { mutableStateOf(false) }
    var showPw by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var signUp by remember { mutableStateOf(false) }
    var name by remember { mutableStateOf("") }
    var sport by remember { mutableStateOf(g.settings.sport) }
    var sports by remember { mutableStateOf<List<Pair<String, String>>>(emptyList()) }

    // Sports are data from the server (never hard-coded in the app).
    LaunchedEffect(server) {
        try {
            sports = g.api.get("/api/v1/sports", auth = "").arr("sports").take(4)
                .mapNotNull { s -> s.str("sport_id")?.let { it to (s.str("name") ?: it) } }
            if (sport.isEmpty() && sports.isNotEmpty()) sport = sports.first().first
        } catch (e: ApiError) { /* offline: the picker stays hidden */ }
    }

    fun submit() {
        if (email.isBlank() || password.isBlank() || (signUp && name.isBlank())) {
            error = if (signUp) "Enter your name, email and a password." else "Enter your email and password."; return
        }
        g.settings.sport = sport
        busy = true; error = null
        g.settings.serverUrl = server
        g.settings.lastEmail = email.trim()
        scope.launch {
            try {
                val login = if (signUp) g.api.post("/api/v1/auth/register", jobj("name" to name.trim(), "email" to email.trim(), "password" to password))
                            else g.api.post("/api/v1/auth/login", jobj("email" to email.trim(), "password" to password))
                val token = login["token"]?.toString()?.trim('"')
                val me = try { g.api.get("/api/v1/me", auth = token) } catch (e: ApiError) { null }
                g.session.signIn(email.trim(), password, login, me)
            } catch (e: ApiError) {
                error = when {
                    e.isNetwork && g.session.signInOffline(email.trim(), password) -> null
                    e.isNetwork -> "Can't reach the server at $server. Check the address and your connection."
                    e.status == 401 -> "That email and password don't match."
                    e.code == "EMAIL_EXISTS" -> "An account with this email already exists. Sign in instead."
                    else -> e.message
                }
            } finally {
                busy = false
            }
        }
    }

    val fieldColors = OutlinedTextFieldDefaults.colors(
        unfocusedContainerColor = MaterialTheme.colorScheme.surface, focusedContainerColor = MaterialTheme.colorScheme.surface,
        unfocusedBorderColor = extra.line,
    )
    val pill = RoundedCornerShape(18.dp)

    Column(
        Modifier.fillMaxSize().background(MaterialTheme.colorScheme.primary).imePadding()
            .verticalScroll(rememberScrollState()),
    ) {
        // Brand header
        Box {
            Stripes(Modifier.matchParentSize())
            Column(
                Modifier.fillMaxWidth().statusBarsPadding().padding(start = 24.dp, end = 24.dp, top = 32.dp, bottom = 36.dp),
                horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Box(Modifier.shadow(12.dp, RoundedCornerShape(28.dp))) { ScorixLogo(104, 28) }
                Text("Scorix", color = Color.White, fontSize = 34.sp, fontWeight = FontWeight.Bold)
                Text("Live scores, standings, clubs and the club store", color = Color.White.copy(alpha = 0.8f), fontSize = 14.sp)
            }
        }
        // Form sheet
        Column(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(topStart = 32.dp, topEnd = 32.dp))
                .background(MaterialTheme.colorScheme.background).navigationBarsPadding().padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Column(Modifier.widthIn(max = 460.dp).fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Text(if (signUp) "Create your account" else "Welcome back", fontSize = 24.sp, fontWeight = FontWeight.Bold)
                Text(if (signUp) "Free, and it takes a few seconds." else "Sign in to follow your league.", color = extra.muted)
                if (sports.isNotEmpty()) {
                    Text("Choose your sport", fontWeight = FontWeight.SemiBold)
                    Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        sports.forEach { (id, label) ->
                            val on = id == sport
                            Box(
                                Modifier.clip(RoundedCornerShape(50))
                                    .background(if (on) extra.ink else MaterialTheme.colorScheme.surface)
                                    .border(1.dp, if (on) extra.ink else extra.line, RoundedCornerShape(50))
                                    .clickable(role = Role.RadioButton, onClickLabel = "Choose $label") { sport = id }
                                    .heightIn(min = 48.dp).padding(horizontal = 18.dp),
                                contentAlignment = Alignment.Center,
                            ) { Text(label, color = if (on) extra.onInk else MaterialTheme.colorScheme.onSurface, fontWeight = FontWeight.SemiBold) }
                        }
                    }
                }
                if (signUp) OutlinedTextField(
                    value = name, onValueChange = { name = it }, label = { Text("Your name") }, singleLine = true, shape = pill,
                    colors = fieldColors, modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = email, onValueChange = { email = it }, label = { Text("Email") }, singleLine = true, shape = pill,
                    leadingIcon = { Icon(Icons.Filled.Mail, null) }, colors = fieldColors,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email, imeAction = ImeAction.Next),
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = password, onValueChange = { password = it }, label = { Text("Password") }, singleLine = true, shape = pill,
                    leadingIcon = { Icon(Icons.Filled.Lock, null) }, colors = fieldColors,
                    visualTransformation = if (showPw) VisualTransformation.None else PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Done),
                    keyboardActions = KeyboardActions(onDone = { submit() }),
                    trailingIcon = {
                        IconButton(onClick = { showPw = !showPw }) {
                            Icon(if (showPw) Icons.Filled.VisibilityOff else Icons.Filled.Visibility,
                                contentDescription = if (showPw) "Hide password" else "Show password")
                        }
                    },
                    isError = error != null,
                    modifier = Modifier.fillMaxWidth(),
                )
                if (error != null) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Icon(Icons.Filled.ErrorOutline, null, tint = MaterialTheme.colorScheme.error, modifier = Modifier.size(16.dp))
                    Text(error!!, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium)
                }
                Button(onClick = { submit() }, enabled = !busy, modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)) {
                    if (busy) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp, color = MaterialTheme.colorScheme.onPrimary)
                    else Text(if (signUp) "Create account" else "Sign in", fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                }
                TextButton(onClick = { signUp = !signUp; error = null }, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)) {
                    Text(if (signUp) "Already have an account? Sign in" else "New to Scorix? Create an account", fontWeight = FontWeight.SemiBold)
                }
                TextButton(onClick = { showServer = !showServer }, modifier = Modifier.heightIn(min = 48.dp)) {
                    Icon(Icons.Filled.Dns, null, modifier = Modifier.size(18.dp))
                    Text("  " + if (showServer) "Hide server settings" else "Server: $server", maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                if (showServer) OutlinedTextField(
                    value = server, onValueChange = { server = it }, label = { Text("Server address") }, singleLine = true, shape = pill,
                    colors = fieldColors,
                    supportingText = { Text("Emulator: http://10.0.2.2:8080 · USB: http://localhost:8080 · Wi-Fi: http://<laptop IP>:8080") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                    modifier = Modifier.fillMaxWidth(),
                )
                Text("Try a demo account", fontSize = 17.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 6.dp))
                demo.forEach { (mail, role) ->
                    val selected = email == mail
                    Row(
                        Modifier.fillMaxWidth().clip(RoundedCornerShape(20.dp))
                            .background(if (selected) extra.ink else MaterialTheme.colorScheme.surface)
                            .border(1.dp, if (selected) extra.ink else extra.line, RoundedCornerShape(20.dp))
                            .clickable(role = Role.Button, onClickLabel = "Use $role account") { email = mail; password = "Nascon@26"; error = null }
                            .heightIn(min = 60.dp).padding(horizontal = 12.dp),
                        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        Avatar(role, 40)
                        Column(Modifier.weight(1f)) {
                            Text(role, fontWeight = FontWeight.SemiBold, color = if (selected) extra.onInk else MaterialTheme.colorScheme.onSurface)
                            Text(mail, fontSize = 12.sp, color = if (selected) extra.onInk.copy(alpha = 0.7f) else extra.muted)
                        }
                        if (selected) Text("Selected", fontSize = 12.sp, color = extra.onInk)
                    }
                }
            }
        }
    }
}
