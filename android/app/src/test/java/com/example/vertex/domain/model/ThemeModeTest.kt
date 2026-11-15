package com.example.vertex.domain.model

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ThemeModeTest {

    @Test
    fun `light is the default theme`() {
        assertEquals(ThemeMode.LIGHT, ThemeMode.DEFAULT)
    }

    @Test
    fun `LIGHT is never dark regardless of system`() {
        assertFalse(ThemeMode.LIGHT.isDark(systemInDarkTheme = true))
        assertFalse(ThemeMode.LIGHT.isDark(systemInDarkTheme = false))
    }

    @Test
    fun `DARK is always dark regardless of system`() {
        assertTrue(ThemeMode.DARK.isDark(systemInDarkTheme = true))
        assertTrue(ThemeMode.DARK.isDark(systemInDarkTheme = false))
    }

    @Test
    fun `SYSTEM follows the system setting`() {
        assertTrue(ThemeMode.SYSTEM.isDark(systemInDarkTheme = true))
        assertFalse(ThemeMode.SYSTEM.isDark(systemInDarkTheme = false))
    }
}
