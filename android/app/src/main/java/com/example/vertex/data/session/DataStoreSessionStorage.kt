package com.example.vertex.data.session

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.emptyPreferences
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import com.example.vertex.core.security.TokenCipher
import com.example.vertex.domain.model.Session
import com.example.vertex.domain.model.User
import com.example.vertex.domain.repository.SessionStorage
import java.io.IOException
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.map

/** Токени зберігаються лише у зашифрованому вигляді, профіль (не секретний) — як є. */
class DataStoreSessionStorage(
    private val dataStore: DataStore<Preferences>,
    private val cipher: TokenCipher,
) : SessionStorage {

    override val session: Flow<Session?> = dataStore.data
        .catch { e -> if (e is IOException) emit(emptyPreferences()) else throw e }
        .map { prefs -> prefs.toSessionOrNull() }

    override suspend fun save(session: Session) {
        dataStore.edit {
            it[ACCESS] = cipher.encrypt(session.accessToken)
            it[REFRESH] = cipher.encrypt(session.refreshToken)
            it[USER_ID] = session.user.id
            it[EMAIL] = session.user.email
            it[USERNAME] = session.user.username
            it[GENDER] = session.user.gender
            it[LANGUAGE] = session.user.language
        }
    }

    override suspend fun clear() {
        dataStore.edit { it.clear() }
    }

    private fun Preferences.toSessionOrNull(): Session? {
        val access = this[ACCESS] ?: return null
        val refresh = this[REFRESH] ?: return null
        val id = this[USER_ID] ?: return null
        return try {
            Session(
                accessToken = cipher.decrypt(access),
                refreshToken = cipher.decrypt(refresh),
                user = User(
                    id = id,
                    email = this[EMAIL].orEmpty(),
                    username = this[USERNAME].orEmpty(),
                    gender = this[GENDER].orEmpty(),
                    language = this[LANGUAGE] ?: "uk",
                ),
            )
        } catch (e: Exception) {
            null // ключ втрачено/дані пошкоджено → вважаємо, що сесії немає (користувач увійде знову)
        }
    }

    internal companion object {
        val ACCESS = stringPreferencesKey("access_enc")
        val REFRESH = stringPreferencesKey("refresh_enc")
        val USER_ID = intPreferencesKey("user_id")
        val EMAIL = stringPreferencesKey("email")
        val USERNAME = stringPreferencesKey("username")
        val GENDER = stringPreferencesKey("gender")
        val LANGUAGE = stringPreferencesKey("language")
    }
}
