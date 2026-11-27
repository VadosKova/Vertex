package com.example.vertex.domain.usecase

import com.example.vertex.domain.model.LoginResult
import com.example.vertex.domain.repository.AuthRepository
import com.example.vertex.domain.repository.SessionStorage

class LoginUseCase(
    private val authRepository: AuthRepository,
    private val sessionStorage: SessionStorage,
) {
    suspend operator fun invoke(email: String, password: String, rememberMe: Boolean): LoginResult {
        val result = authRepository.login(
            email = email.trim().lowercase(),
            password = password, // пароль не обрізаємо і не змінюємо
            rememberMe = rememberMe,
        )
        if (result is LoginResult.Success) sessionStorage.save(result.session)
        return result
    }
}
