package com.example.vertex.data.auth

import com.example.vertex.domain.model.AuthError
import com.example.vertex.domain.model.LoginResult
import java.io.IOException
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.Json
import okhttp3.Protocol
import okhttp3.Request
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.HttpException
import retrofit2.Response

class RemoteAuthRepositoryTest {

    private fun repoThatThrows(t: Throwable) = RemoteAuthRepository(object : AuthApi {
        override suspend fun login(body: LoginRequest): LoginResponse = throw t
    })

    private fun httpError(code: Int, retryAfter: String? = null): HttpException {
        val raw = okhttp3.Response.Builder()
            .code(code).message("error").protocol(Protocol.HTTP_1_1)
            .request(Request.Builder().url("http://localhost/").build())
            .apply { if (retryAfter != null) header("Retry-After", retryAfter) }
            .build()
        return HttpException(Response.error<Any>("".toResponseBody(null), raw))
    }

    private suspend fun failureOf(t: Throwable): AuthError =
        (repoThatThrows(t).login("a@b.co", "x", true) as LoginResult.Failure).error

    @Test fun `401 and 400 map to InvalidCredentials`() = runTest {
        assertEquals(AuthError.InvalidCredentials, failureOf(httpError(401)))
        assertEquals(AuthError.InvalidCredentials, failureOf(httpError(400)))
    }

    @Test fun `429 maps to TooManyRequests with Retry-After`() = runTest {
        assertEquals(AuthError.TooManyRequests(30), failureOf(httpError(429, "30")))
        assertEquals(AuthError.TooManyRequests(null), failureOf(httpError(429)))
    }

    @Test fun `5xx maps to Server`() = runTest {
        assertEquals(AuthError.Server, failureOf(httpError(500)))
        assertEquals(AuthError.Server, failureOf(httpError(503)))
    }

    @Test fun `other HTTP codes map to Unknown`() = runTest {
        assertEquals(AuthError.Unknown, failureOf(httpError(418)))
    }

    @Test fun `IO problems map to NetworkUnavailable`() = runTest {
        assertEquals(AuthError.NetworkUnavailable, failureOf(IOException("timeout")))
    }

    @Test fun `unparsable response maps to Server`() = runTest {
        assertEquals(AuthError.Server, failureOf(SerializationException("bad json")))
    }

    @Test fun `success returns mapped session and sends request fields`() = runTest {
        var sent: LoginRequest? = null
        val repo = RemoteAuthRepository(object : AuthApi {
            override suspend fun login(body: LoginRequest): LoginResponse {
                sent = body
                return LoginResponse("acc", "ref", UserDto(3, "a@b.co", "Anna", "female", "uk"))
            }
        })
        val result = repo.login("a@b.co", "Secret1!", rememberMe = false)
        assertTrue(result is LoginResult.Success)
        val session = (result as LoginResult.Success).session
        assertEquals("acc", session.accessToken)
        assertEquals("ref", session.refreshToken)
        assertEquals("Anna", session.user.username)
        assertEquals(LoginRequest("a@b.co", "Secret1!", false), sent)
    }

    @Test(expected = kotlinx.coroutines.CancellationException::class)
    fun `cancellation is propagated, not swallowed`() = runTest {
        repoThatThrows(kotlinx.coroutines.CancellationException("cancelled")).login("a@b.co", "x", true)
    }
}
