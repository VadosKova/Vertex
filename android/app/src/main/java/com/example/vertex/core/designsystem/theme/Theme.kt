package com.example.vertex.core.designsystem.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.runtime.staticCompositionLocalOf

private val LocalExtraColors = staticCompositionLocalOf { LightExtraColors }
private val LocalIsDarkTheme = staticCompositionLocalOf { false }

object VertexTheme {
    val extraColors: VertexExtraColors
        @Composable @ReadOnlyComposable get() = LocalExtraColors.current

    val isDark: Boolean
        @Composable @ReadOnlyComposable get() = LocalIsDarkTheme.current
}

@Composable
fun VertexTheme(
    darkTheme: Boolean,
    content: @Composable () -> Unit,
) {
    CompositionLocalProvider(
        LocalExtraColors provides if (darkTheme) DarkExtraColors else LightExtraColors,
        LocalIsDarkTheme provides darkTheme,
    ) {
        MaterialTheme(
            colorScheme = if (darkTheme) DarkColorScheme else LightColorScheme,
            typography = VertexTypography,
            content = content,
        )
    }
}
