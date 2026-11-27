package com.example.vertex.data.auth

import retrofit2.http.Body
import retrofit2.http.POST

interface AuthApi {
    @POST("auth/token/")
    suspend fun login(@Body body: LoginRequest): LoginResponse
}
