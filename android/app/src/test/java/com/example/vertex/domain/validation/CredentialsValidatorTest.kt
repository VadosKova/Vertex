package com.example.vertex.domain.validation

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class CredentialsValidatorTest {

    @Test fun `blank email is EMPTY`() {
        assertEquals(FieldError.EMPTY, CredentialsValidator.validateEmail(""))
        assertEquals(FieldError.EMPTY, CredentialsValidator.validateEmail("   "))
    }

    @Test fun `malformed emails are INVALID_EMAIL`() {
        listOf("john", "john@", "@example.com", "john@example", "jo hn@example.com", "a@@b.com")
            .forEach { assertEquals(it, FieldError.INVALID_EMAIL, CredentialsValidator.validateEmail(it)) }
    }

    @Test fun `valid emails pass, surrounding spaces are ignored`() {
        listOf("john.doe@example.com", "a@b.co", "  user+tag@mail.example.org  ")
            .forEach { assertNull(it, CredentialsValidator.validateEmail(it)) }
    }

    @Test fun `empty password is rejected, any non-empty password passes`() {
        assertEquals(FieldError.EMPTY, CredentialsValidator.validatePassword(""))
        assertNull(CredentialsValidator.validatePassword("x"))
        assertNull(CredentialsValidator.validatePassword("   "))
    }
}
