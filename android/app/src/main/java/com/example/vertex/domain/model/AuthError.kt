package com.example.vertex.domain.model

sealed interface AuthError {
    /** 400/401: невірні дані для входу. */
    data object InvalidCredentials : AuthError

    /** Немає мережі / таймаут / сервер недосяжний. */
    data object NetworkUnavailable : AuthError

    /** 429: перевищено ліміт спроб (на бекенді scope "auth": 30/хв). */
    data class TooManyRequests(val retryAfterSeconds: Int?) : AuthError

    /** 5xx або нерозбірлива відповідь сервера. */
    data object Server : AuthError

    data object Unknown : AuthError
}

sealed interface LoginResult {
    data class Success(val session: Session) : LoginResult
    data class Failure(val error: AuthError) : LoginResult
}
