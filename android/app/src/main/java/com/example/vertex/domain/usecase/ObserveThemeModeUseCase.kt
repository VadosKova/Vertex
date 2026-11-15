package com.example.vertex.domain.usecase

import com.example.vertex.domain.model.ThemeMode
import com.example.vertex.domain.repository.SettingsRepository
import kotlinx.coroutines.flow.Flow

class ObserveThemeModeUseCase constructor(
    private val repository: SettingsRepository,
) {
    operator fun invoke(): Flow<ThemeMode> = repository.themeMode
}
