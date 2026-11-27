package com.example.vertex.domain.usecase

import com.example.vertex.domain.model.AuthError
import com.example.vertex.domain.model.LoginResult
import com.example.vertex.testutil.FakeAuthRepository
import com.example.vertex.testutil.FakeSessionStorage
import com.example.vertex.testutil.TEST_SESSION
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class LoginUseCaseTest {
    private val repo = FakeAuthRepository()
    private val storage = FakeSessionStorage()
    private val useCase = LoginUseCase(repo, storage)

    @Test fun `success saves the session`() = runTest {
        val result = useCase("john@example.com", "Secret1!", rememberMe = true)
        assertEquals(LoginResult.Success(TEST_SESSION), result)
        assertEquals(TEST_SESSION, storage.state.value)
    }

    @Test fun `failure does not save anything`() = runTest {
        repo.result = LoginResult.Failure(AuthError.InvalidCredentials)
        val result = useCase("john@example.com", "wrong", rememberMe = true)
        assertEquals(LoginResult.Failure(AuthError.InvalidCredentials), result)
        assertNull(storage.state.value)
    }

    @Test fun `email is trimmed and lowercased, password is sent untouched`() = runTest {
        useCase("  John.Doe@Example.COM ", "  Pa ss  ", rememberMe = false)
        assertEquals(
            FakeAuthRepository.Call("john.doe@example.com", "  Pa ss  ", false),
            repo.calls.single(),
        )
    }
}
