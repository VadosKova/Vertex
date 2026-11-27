package com.example.vertex.testutil

import com.example.vertex.core.security.TokenCipher
import com.example.vertex.domain.model.LoginResult
import com.example.vertex.domain.model.Session
import com.example.vertex.domain.model.User
import com.example.vertex.domain.repository.AuthRepository
import com.example.vertex.domain.repository.SessionStorage
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow

val TEST_USER = User(id = 7, email = "john@example.com", username = "John", gender = "male", language = "uk")
val TEST_SESSION = Session(accessToken = "access-token-123", refreshToken = "refresh-token-456", user = TEST_USER)

class FakeAuthRepository(var result: LoginResult = LoginResult.Success(TEST_SESSION)) : AuthRepository {
    data class Call(val email: String, val password: String, val rememberMe: Boolean)

    val calls = mutableListOf<Call>()

    override suspend fun login(email: String, password: String, rememberMe: Boolean): LoginResult {
        calls += Call(email, password, rememberMe)
        return result
    }
}

class FakeSessionStorage : SessionStorage {
    val state = MutableStateFlow<Session?>(null)
    override val session: Flow<Session?> = state
    override suspend fun save(session: Session) { state.value = session }
    override suspend fun clear() { state.value = null }
}

/** Оборотне «шифрування» для JVM-тестів (Android Keystore там недоступний). */
class FakeTokenCipher : TokenCipher {
    override fun encrypt(plain: String) = "enc(" + plain.reversed() + ")"
    override fun decrypt(encoded: String) = encoded.removePrefix("enc(").removeSuffix(")").reversed()
}
