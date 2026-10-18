package com.nascon.app

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.nascon.app.ui.AppTheme
import com.nascon.app.ui.DeepLink
import com.nascon.app.ui.DeepLinkScreen
import com.nascon.app.ui.LoginScreen
import com.nascon.app.ui.MainScreen

class MainActivity : ComponentActivity() {
    private var deepLink by mutableStateOf<DeepLink?>(null)

    @OptIn(ExperimentalComposeUiApi::class)
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge(statusBarStyle = androidx.activity.SystemBarStyle.dark(android.graphics.Color.TRANSPARENT))
        deepLink = DeepLink.parse(intent?.data)
        val g = (application as App).graph
        setContent {
            val session by g.session.state.collectAsStateWithLifecycle()
            // A deep link opens its screen straight away (spec 6.3: foreground within 2 s, no login wall).
            var splash by androidx.compose.runtime.saveable.rememberSaveable { mutableStateOf(deepLink == null) }
            androidx.compose.runtime.LaunchedEffect(Unit) { kotlinx.coroutines.delay(1600); splash = false }
            AppTheme(session?.branding) {
                Box(Modifier.fillMaxSize().semantics { testTagsAsResourceId = true }) {
                    val link = deepLink
                    androidx.compose.animation.Crossfade(targetState = splash && link == null, label = "splash") { show ->
                        when {
                            link != null -> Box(Modifier.safeDrawingPadding()) { DeepLinkScreen(link) { deepLink = null } }
                            show -> com.nascon.app.ui.SplashScreen()
                            session == null -> LoginScreen()
                            else -> MainScreen(session!!)
                        }
                    }
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        DeepLink.parse(intent.data)?.let { deepLink = it }
    }
}

@Composable
fun graph(): Graph = (LocalContext.current.applicationContext as App).graph
