package com.example.vertex.domain.model

data class User(
    val id: Int,
    val email: String,
    val username: String,
    val gender: String,
    val language: String,
)

data class Session(
    val accessToken: String,
    val refreshToken: String,
    val user: User,
)
