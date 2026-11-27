package com.example.vertex

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.preferencesDataStore
import com.example.vertex.core.network.ApiClient
import com.example.vertex.core.security.KeystoreTokenCipher
import com.example.vertex.data.auth.AuthApi
import com.example.vertex.data.auth.RemoteAuthRepository
import com.example.vertex.data.session.DataStoreSessionStorage
import com.example.vertex.data.settings.DataStoreSettingsRepository
import com.example.vertex.domain.repository.SessionStorage
import com.example.vertex.domain.repository.SettingsRepository
import com.example.vertex.domain.usecase.LoginUseCase
import com.example.vertex.domain.usecase.ObserveThemeModeUseCase
import com.example.vertex.domain.usecase.SetThemeModeUseCase

private val Context.settingsDataStore: DataStore<Preferences> by preferencesDataStore(name = "vertex_settings")
private val Context.sessionDataStore: DataStore<Preferences> by preferencesDataStore(name = "vertex_session")

/**
 * Ручний DI (без kapt/KSP). Важкі об'єкти (Retrofit, Keystore) створюються ліниво,
 * щоб не сповільнювати холодний старт.
 */
class AppContainer(context: Context) {
    private val appContext = context.applicationContext

    // --- налаштування (тема) ---
    private val settingsRepository: SettingsRepository =
        DataStoreSettingsRepository(appContext.settingsDataStore)
    val observeThemeMode = ObserveThemeModeUseCase(settingsRepository)
    val setThemeMode = SetThemeModeUseCase(settingsRepository)

    // --- авторизація ---
    private val authApi: AuthApi by lazy {
        ApiClient.createRetrofit(BuildConfig.API_BASE_URL).create(AuthApi::class.java)
    }
    private val sessionStorage: SessionStorage by lazy {
        DataStoreSessionStorage(appContext.sessionDataStore, KeystoreTokenCipher())
    }
    val loginUseCase: LoginUseCase by lazy {
        LoginUseCase(RemoteAuthRepository(authApi), sessionStorage)
    }
}
