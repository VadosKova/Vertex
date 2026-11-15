package com.example.vertex

import android.app.Application
import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.preferencesDataStore
import com.example.vertex.data.settings.DataStoreSettingsRepository
import com.example.vertex.domain.repository.SettingsRepository
import com.example.vertex.domain.usecase.ObserveThemeModeUseCase
import com.example.vertex.domain.usecase.SetThemeModeUseCase

private val Context.settingsDataStore: DataStore<Preferences> by preferencesDataStore(name = "vertex_settings")

class VertexApp : Application() {
    val container: AppContainer by lazy { AppContainer(this) }
}

class AppContainer(context: Context) {
    private val settingsRepository: SettingsRepository =
        DataStoreSettingsRepository(context.applicationContext.settingsDataStore)

    val observeThemeMode = ObserveThemeModeUseCase(settingsRepository)
    val setThemeMode = SetThemeModeUseCase(settingsRepository)
}
