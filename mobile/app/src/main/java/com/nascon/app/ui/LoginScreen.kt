package com.nascon.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ErrorOutline
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
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
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import com.nascon.app.data.ApiError
import com.nascon.app.data.jobj
import com.nascon.app.graph
import kotlinx.coroutines.launch

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

    fun submit() {
        if (email.isBlank() || password.isBlank()) {
            error = "Enter your email and password."; return
        }
        busy = true; error = null
        g.settings.serverUrl = server
        g.settings.lastEmail = email.trim()
        scope.launch {
            try {
                val login = g.api.post("/api/v1/auth/login", jobj("email" to email.trim(), "password" to password))
                val token = login["token"]?.toString()?.trim('"')
                val me = try { g.api.get("/api/v1/me", auth = token) } catch (e: ApiError) { null }
                g.session.signIn(email.trim(), password, login, me)
            } catch (e: ApiError) {
                error = when {
                    e.isNetwork && g.session.signInOffline(email.trim(), password) -> null
                    e.isNetwork -> "Can't reach the server at $server. Check the address and your connection."
                    e.status == 401 -> "That email and password don't match."
                    else -> e.message
                }
            } finally {
                busy = false
            }
        }
    }

    Column(
        Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).safeDrawingPadding().imePadding()
            .verticalScroll(rememberScrollState()).padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Column(Modifier.widthIn(max = 420.dp).fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Row(Modifier.padding(top = 24.dp, bottom = 8.dp), verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Logo("AS", 40)
                Column {
                    Text("Alpha Sports", style = MaterialTheme.typography.titleLarge)
                    Text("Fixtures, standings, club and store", color = extra.muted, style = MaterialTheme.typography.bodyMedium)
                }
            }
            OutlinedTextField(
                value = email, onValueChange = { email = it }, label = { Text("Email") }, singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email, imeAction = ImeAction.Next),
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = password, onValueChange = { password = it }, label = { Text("Password") }, singleLine = true,
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
            Button(onClick = { submit() }, enabled = !busy, modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp)) {
                if (busy) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp, color = MaterialTheme.colorScheme.onPrimary)
                else Text("Sign in")
            }
            TextButton(onClick = { showServer = !showServer }, modifier = Modifier.heightIn(min = 48.dp)) {
                Text(if (showServer) "Hide server settings" else "Server: $server")
            }
            if (showServer) {
                OutlinedTextField(
                    value = server, onValueChange = { server = it }, label = { Text("Server address") }, singleLine = true,
                    supportingText = { Text("Emulator: http://10.0.2.2:8080 · Phone: http://<laptop LAN IP>:8080") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            Text("Demo accounts", style = MaterialTheme.typography.labelSmall, color = extra.muted, modifier = Modifier.padding(top = 8.dp))
            listOf(
                "organizer@nascon.test" to "League organiser",
                "manager@nascon.test" to "Club manager",
                "player@nascon.test" to "Player",
                "viewer@nascon.test" to "Viewer",
                "admin@nascon.test" to "Platform admin",
            ).forEach { (mail, role) ->
                RowItem(onClick = { email = mail; password = "Nascon@26" }) {
                    Row(Modifier.fillMaxWidth()) {
                        Text(role, modifier = Modifier.weight(1f))
                        Text(mail, color = extra.muted, style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
        }
    }
}
