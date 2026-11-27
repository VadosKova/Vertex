package com.example.vertex.domain.repository

import com.example.vertex.domain.model.LoginResult

interface AuthRepository {
    suspend fun login(email: String, password: String, rememberMe: Boolean): LoginResult
}
