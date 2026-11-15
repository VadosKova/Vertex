package com.example.vertex.testutil

import com.example.vertex.domain.model.ThemeMode
import com.example.vertex.domain.repository.SettingsRepository
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow

class FakeSettingsRepository(initial: ThemeMode = ThemeMode.DEFAULT) : SettingsRepository {
    val state = MutableStateFlow(initial)
    override val themeMode: Flow<ThemeMode> = state
    override suspend fun setThemeMode(mode: ThemeMode) {
        state.value = mode
    }
}
