package com.example.vertex.feature.login

import com.example.vertex.domain.model.AuthError
import com.example.vertex.domain.validation.FieldError

/** Помилка форми цілком (показується банером над полями). */
enum class FormError { INVALID_CREDENTIALS, NETWORK, TOO_MANY_REQUESTS, SERVER, UNKNOWN }

data class LoginUiState(
    val email: String = "",
    val password: String = "",
    val rememberMe: Boolean = true, // як у макеті: за замовчуванням увімкнено
    val isPasswordVisible: Boolean = false,
    val isLoading: Boolean = false,
    val emailError: FieldError? = null,
    val passwordError: FieldError? = null,
    val formError: FormError? = null,
)

sealed interface LoginEvent {
    data object LoggedIn : LoginEvent
}

internal fun AuthError.toFormError(): FormError = when (this) {
    AuthError.InvalidCredentials -> FormError.INVALID_CREDENTIALS
    AuthError.NetworkUnavailable -> FormError.NETWORK
    is AuthError.TooManyRequests -> FormError.TOO_MANY_REQUESTS
    AuthError.Server -> FormError.SERVER
    AuthError.Unknown -> FormError.UNKNOWN
}
