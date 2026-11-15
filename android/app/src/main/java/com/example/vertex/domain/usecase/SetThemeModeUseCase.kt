package com.example.vertex.domain.usecase

import com.example.vertex.domain.model.ThemeMode
import com.example.vertex.domain.repository.SettingsRepository

class SetThemeModeUseCase constructor(
    private val repository: SettingsRepository,
) {
    suspend operator fun invoke(mode: ThemeMode) = repository.setThemeMode(mode)
}
