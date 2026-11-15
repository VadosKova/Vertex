package com.example.vertex.data.settings

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.emptyPreferences
import androidx.datastore.preferences.core.stringPreferencesKey
import com.example.vertex.domain.model.ThemeMode
import com.example.vertex.domain.repository.SettingsRepository
import java.io.IOException
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map

class DataStoreSettingsRepository constructor(
    private val dataStore: DataStore<Preferences>,
) : SettingsRepository {

    override val themeMode: Flow<ThemeMode> = dataStore.data
        .catch { e -> if (e is IOException) emit(emptyPreferences()) else throw e }
        .map { prefs -> prefs[THEME_MODE_KEY].toThemeModeOrDefault() }
        .distinctUntilChanged()

    override suspend fun setThemeMode(mode: ThemeMode) {
        dataStore.edit { it[THEME_MODE_KEY] = mode.name }
    }

    private fun String?.toThemeModeOrDefault(): ThemeMode =
        ThemeMode.entries.firstOrNull { it.name == this } ?: ThemeMode.DEFAULT

    internal companion object {
        val THEME_MODE_KEY = stringPreferencesKey("theme_mode")
    }
}
