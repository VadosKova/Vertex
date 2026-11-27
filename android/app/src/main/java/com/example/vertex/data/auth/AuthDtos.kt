package com.example.vertex.data.auth

import com.example.vertex.domain.model.Session
import com.example.vertex.domain.model.User
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class LoginRequest(
    val email: String,
    val password: String,
    @SerialName("remember_me") val rememberMe: Boolean,
)

@Serializable
data class UserDto(
    val id: Int,
    val email: String,
    val username: String,
    val gender: String = "",
    val language: String = "uk",
)

@Serializable
data class LoginResponse(
    val access: String,
    val refresh: String,
    val user: UserDto,
)

fun LoginResponse.toSession() = Session(
    accessToken = access,
    refreshToken = refresh,
    user = User(user.id, user.email, user.username, user.gender, user.language),
)
