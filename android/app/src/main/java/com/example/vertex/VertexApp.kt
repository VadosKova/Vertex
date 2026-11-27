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

class VertexApp : Application() {
    val container: AppContainer by lazy { AppContainer(this) }
}