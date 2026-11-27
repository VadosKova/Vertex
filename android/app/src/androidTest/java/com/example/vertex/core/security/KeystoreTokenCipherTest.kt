package com.example.vertex.core.security

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Test

class KeystoreTokenCipherTest {
    private val cipher = KeystoreTokenCipher(alias = "vertex_test_key")

    @Test fun roundTrip() {
        val token = "eyJhbGciOi.header.payload.signature-ÄÖ-тест"
        assertEquals(token, cipher.decrypt(cipher.encrypt(token)))
    }

    @Test fun ciphertextHidesPlaintext() {
        val encrypted = cipher.encrypt("secret-token")
        assertFalse(encrypted.contains("secret-token"))
    }

    @Test fun eachEncryptionUsesFreshIv() {
        assertNotEquals(cipher.encrypt("same"), cipher.encrypt("same"))
    }
}
