package com.example.vertex.domain.validation

enum class FieldError { EMPTY, INVALID_EMAIL }

/** Чиста Kotlin-валідація (без android.util.Patterns), тому легко тестується на JVM. */
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

    /** На вході пароль лише має бути непорожнім: правила складності перевіряє сервер при реєстрації. */
    fun validatePassword(password: String): FieldError? =
        if (password.isEmpty()) FieldError.EMPTY else null
}
