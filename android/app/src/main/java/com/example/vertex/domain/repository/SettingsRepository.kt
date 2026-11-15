package com.example.vertex.domain.repository

import com.example.vertex.domain.model.ThemeMode
import kotlinx.coroutines.flow.Flow

interface SettingsRepository {
    val themeMode: Flow<ThemeMode>
    suspend fun setThemeMode(mode: ThemeMode)
}
