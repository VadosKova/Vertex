package com.example.vertex.data.settings

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import com.example.vertex.domain.model.ThemeMode
import java.io.File
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class DataStoreSettingsRepositoryTest {

    @get:Rule
    val tmp = TemporaryFolder()

    private fun TestScope.createDataStore(): DataStore<Preferences> =
        PreferenceDataStoreFactory.create(scope = backgroundScope) {
            File(tmp.root, "test.preferences_pb")
        }

    @Test
    fun `returns default when nothing is stored`() = runTest {
        val repo = DataStoreSettingsRepository(createDataStore())
        assertEquals(ThemeMode.DEFAULT, repo.themeMode.first())
    }

    @Test
    fun `persists and reads back the chosen theme`() = runTest {
        val repo = DataStoreSettingsRepository(createDataStore())

        repo.setThemeMode(ThemeMode.DARK)
        assertEquals(ThemeMode.DARK, repo.themeMode.first())

        repo.setThemeMode(ThemeMode.LIGHT)
        assertEquals(ThemeMode.LIGHT, repo.themeMode.first())
    }

    @Test
    fun `falls back to default on an unknown stored value`() = runTest {
        val dataStore = createDataStore()
        dataStore.edit { it[DataStoreSettingsRepository.THEME_MODE_KEY] = "NEON_PINK" }

        val repo = DataStoreSettingsRepository(dataStore)
        assertEquals(ThemeMode.DEFAULT, repo.themeMode.first())
    }
}
