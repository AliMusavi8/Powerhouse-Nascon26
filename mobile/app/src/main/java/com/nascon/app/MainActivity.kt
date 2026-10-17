package com.nascon.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
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
            AppTheme(session?.branding) {
                if (session == null) LoginScreen() else MainScreen(session!!)
            }
        }
    }
}

@Composable
fun graph(): Graph = (LocalContext.current.applicationContext as App).graph
