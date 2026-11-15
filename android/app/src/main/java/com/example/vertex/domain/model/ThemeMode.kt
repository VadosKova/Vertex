package com.example.vertex.domain.model

enum class ThemeMode {
    SYSTEM,
    LIGHT,
    DARK;

    fun isDark(systemInDarkTheme: Boolean): Boolean = when (this) {
        SYSTEM -> systemInDarkTheme
        LIGHT -> false
        DARK -> true
    }

    companion object {
        /** Світла тема — тема за замовчуванням (рішення з дизайну). Для «як у системі» постав SYSTEM. */
        val DEFAULT: ThemeMode = LIGHT
    }
}
