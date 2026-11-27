package com.example.vertex.data.auth

import com.example.vertex.domain.model.AuthError
import com.example.vertex.domain.model.LoginResult
import com.example.vertex.domain.repository.AuthRepository
import java.io.IOException
import kotlinx.coroutines.CancellationException
import kotlinx.serialization.SerializationException
import retrofit2.HttpException

class RemoteAuthRepository(private val api: AuthApi) : AuthRepository {

    override suspend fun login(email: String, password: String, rememberMe: Boolean): LoginResult =
        try {
            LoginResult.Success(api.login(LoginRequest(email, password, rememberMe)).toSession())
        } catch (e: CancellationException) {
            throw e // не ковтаємо скасування корутини
        } catch (e: HttpException) {
            LoginResult.Failure(e.toAuthError())
        } catch (e: IOException) {
            LoginResult.Failure(AuthError.NetworkUnavailable)
        } catch (e: SerializationException) {
            LoginResult.Failure(AuthError.Server)
        }
}

internal fun HttpException.toAuthError(): AuthError = when (code()) {
    400, 401 -> AuthError.InvalidCredentials
    429 -> AuthError.TooManyRequests(response()?.headers()?.get("Retry-After")?.toIntOrNull())
    in 500..599 -> AuthError.Server
    else -> AuthError.Unknown
}
