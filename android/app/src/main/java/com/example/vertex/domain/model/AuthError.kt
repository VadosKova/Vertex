package com.example.vertex.domain.model

sealed interface AuthError {
    data object InvalidCredentials : AuthError

    data object NetworkUnavailable : AuthError

    data class TooManyRequests(val retryAfterSeconds: Int?) : AuthError

    data object Server : AuthError

    data object Unknown : AuthError
}

sealed interface LoginResult {
    data class Success(val session: Session) : LoginResult
    data class Failure(val error: AuthError) : LoginResult
}
