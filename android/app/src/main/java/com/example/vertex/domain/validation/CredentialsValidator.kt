package com.example.vertex.domain.validation

enum class FieldError { EMPTY, INVALID_EMAIL }

object CredentialsValidator {
    private val EMAIL = Regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$")

    fun validateEmail(email: String): FieldError? {
        val value = email.trim()
        return when {
            value.isEmpty() -> FieldError.EMPTY
            !EMAIL.matches(value) -> FieldError.INVALID_EMAIL
            else -> null
        }
    }

    fun validatePassword(password: String): FieldError? =
        if (password.isEmpty()) FieldError.EMPTY else null
}
