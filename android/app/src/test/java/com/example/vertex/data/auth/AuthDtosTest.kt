package com.example.vertex.data.auth

import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test


class AuthDtosTest {
    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }

    @Test fun `request uses snake_case remember_me`() {
        val body = json.encodeToString(LoginRequest("a@b.co", "pw", rememberMe = true))
        assertTrue(body, body.contains("\"remember_me\":true"))
        assertTrue(body, body.contains("\"email\":\"a@b.co\""))
    }

    @Test fun `parses server response and ignores extra fields`() {
        val payload = """
            {"refresh":"r.r.r","access":"a.a.a","user":{"id":5,"email":"john@example.com","username":"John",
             "gender":"male","language":"uk","theme":"system","reminder_enabled":true,"reminder_day":1,
             "reminder_time":"10:00","timezone":"Europe/Kyiv","push_enabled":true,"in_app_enabled":true}}
        """.trimIndent()
        val session = json.decodeFromString<LoginResponse>(payload).toSession()
        assertEquals("a.a.a", session.accessToken)
        assertEquals("r.r.r", session.refreshToken)
        assertEquals(5, session.user.id)
        assertEquals("John", session.user.username)
    }

    @Test fun `gender may be empty for accounts without a profile`() {
        val payload = """{"refresh":"r","access":"a","user":{"id":1,"email":"x@y.zz","username":"X","gender":""}}"""
        assertEquals("", json.decodeFromString<LoginResponse>(payload).user.gender)
    }
}
