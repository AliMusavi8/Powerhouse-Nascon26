package com.nascon.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.nascon.app.ui.AppTheme
import com.nascon.app.ui.LoginScreen
import com.nascon.app.ui.MainScreen

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge(statusBarStyle = androidx.activity.SystemBarStyle.dark(android.graphics.Color.TRANSPARENT))
        val g = (application as App).graph
        setContent {
            val session by g.session.state.collectAsStateWithLifecycle()
            var splash by androidx.compose.runtime.saveable.rememberSaveable { androidx.compose.runtime.mutableStateOf(true) }
            androidx.compose.runtime.LaunchedEffect(Unit) { kotlinx.coroutines.delay(1600); splash = false }
            AppTheme(session?.branding) {
                androidx.compose.animation.Crossfade(targetState = splash, label = "splash") { show ->
                    when {
                        show -> com.nascon.app.ui.SplashScreen()
                        session == null -> LoginScreen()
                        else -> MainScreen(session!!)
                    }
                }
            }
        }
    }
}

@Composable
fun graph(): Graph = (LocalContext.current.applicationContext as App).graph
