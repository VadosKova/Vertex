package com.example.vertex.core.designsystem.theme

import androidx.compose.material3.ColorScheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Immutable
import androidx.compose.ui.graphics.Color


internal object VertexPalette {
    val LightBackground = Color(0xFFF8F9FA)
    val LightSurface = Color(0xFFFFFFFF)
    val LightTextPrimary = Color(0xFF1A1C1E)
    val LightTextSecondary = Color(0xFF6C757D)
    val LightPrimary = Color(0xFF8B5CF6)
    val LightPrimaryVariant = Color(0xFF7C3AED)

    val DarkBackground = Color(0xFF0F172A)
    val DarkSurface = Color(0xFF1E293B)
    val DarkTextPrimary = Color(0xFFF1F5F9)
    val DarkTextSecondary = Color(0xFF94A3B8)
    val DarkPrimary = Color(0xFFC618FF)
    val DarkPrimaryVariant = Color(0xFFD946EF)
}

internal val LightColorScheme: ColorScheme = lightColorScheme(
    primary = VertexPalette.LightPrimary,
    onPrimary = Color.White,
    background = VertexPalette.LightBackground,
    onBackground = VertexPalette.LightTextPrimary,
    surface = VertexPalette.LightSurface,
    onSurface = VertexPalette.LightTextPrimary,
    onSurfaceVariant = VertexPalette.LightTextSecondary,
    outline = VertexPalette.LightTextSecondary,
)

internal val DarkColorScheme: ColorScheme = darkColorScheme(
    primary = VertexPalette.DarkPrimary,
    onPrimary = Color.White,
    background = VertexPalette.DarkBackground,
    onBackground = VertexPalette.DarkTextPrimary,
    surface = VertexPalette.DarkSurface,
    onSurface = VertexPalette.DarkTextPrimary,
    onSurfaceVariant = VertexPalette.DarkTextSecondary,
    outline = VertexPalette.DarkTextSecondary,
)


@Immutable
data class VertexExtraColors(
    val primaryVariant: Color,
    val buttonShadow: Color,
    val logoGlow: Color,
    val borderSubtle: Color,
)

internal val LightExtraColors = VertexExtraColors(
    primaryVariant = VertexPalette.LightPrimaryVariant,
    buttonShadow = Color(0x59C618FF),
    logoGlow = VertexPalette.LightPrimary.copy(alpha = 0.30f),
    borderSubtle = VertexPalette.LightTextSecondary.copy(alpha = 0.25f),
)

internal val DarkExtraColors = VertexExtraColors(
    primaryVariant = VertexPalette.DarkPrimaryVariant,
    buttonShadow = Color(0x59C618FF),
    logoGlow = VertexPalette.DarkPrimary.copy(alpha = 0.35f),
    borderSubtle = VertexPalette.DarkTextSecondary.copy(alpha = 0.25f),
)
