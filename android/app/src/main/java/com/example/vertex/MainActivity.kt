package com.example.vertex

import android.graphics.Color
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.example.vertex.core.designsystem.theme.VertexTheme
import com.example.vertex.domain.model.ThemeMode
import com.example.vertex.navigation.VertexNavHost

class MainActivity : ComponentActivity() {

    private val viewModel: MainViewModel by viewModels { MainViewModel.Factory }

    override fun onCreate(savedInstanceState: Bundle?) {
        val splash = installSplashScreen()
        super.onCreate(savedInstanceState)
        splash.setKeepOnScreenCondition { viewModel.themeMode.value == null }

        setContent {
            val mode by viewModel.themeMode.collectAsStateWithLifecycle()
            val darkTheme = (mode ?: ThemeMode.DEFAULT).isDark(isSystemInDarkTheme())

            DisposableEffect(darkTheme) {
                enableEdgeToEdge(
                    statusBarStyle = SystemBarStyle.auto(Color.TRANSPARENT, Color.TRANSPARENT) { darkTheme },
                    navigationBarStyle = SystemBarStyle.auto(Color.TRANSPARENT, Color.TRANSPARENT) { darkTheme },
                )
                onDispose { }
            }

            VertexTheme(darkTheme = darkTheme) {
                VertexNavHost()
            }
        }
    }
}
