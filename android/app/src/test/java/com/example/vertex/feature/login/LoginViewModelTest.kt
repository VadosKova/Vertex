package com.example.vertex.feature.login

import com.example.vertex.domain.model.AuthError
import com.example.vertex.domain.model.LoginResult
import com.example.vertex.domain.usecase.LoginUseCase
import com.example.vertex.domain.validation.FieldError
import com.example.vertex.testutil.FakeAuthRepository
import com.example.vertex.testutil.FakeSessionStorage
import com.example.vertex.testutil.MainDispatcherRule
import com.example.vertex.testutil.TEST_SESSION
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class LoginViewModelTest {
    @get:Rule val mainDispatcherRule = MainDispatcherRule()

    private val repo = FakeAuthRepository()
    private val storage = FakeSessionStorage()
    private fun vm() = LoginViewModel(LoginUseCase(repo, storage))

    private fun LoginViewModel.fill(email: String = "john@example.com", password: String = "Secret1!") {
        onEmailChange(email); onPasswordChange(password)
    }

    @Test fun `initial state matches the design`() {
        val s = vm().state.value
        assertTrue("remember me is on by default", s.rememberMe)
        assertFalse(s.isPasswordVisible); assertFalse(s.isLoading)
        assertNull(s.formError)
    }

    @Test fun `empty fields show errors and make no request`() {
        val vm = vm()
        vm.onSubmit()
        assertEquals(FieldError.EMPTY, vm.state.value.emailError)
        assertEquals(FieldError.EMPTY, vm.state.value.passwordError)
        assertTrue(repo.calls.isEmpty())
    }

    @Test fun `malformed email shows INVALID_EMAIL and makes no request`() {
        val vm = vm().apply { fill(email = "not-an-email") }
        vm.onSubmit()
        assertEquals(FieldError.INVALID_EMAIL, vm.state.value.emailError)
        assertNull(vm.state.value.passwordError)
        assertTrue(repo.calls.isEmpty())
    }

    @Test fun `successful login stores session, emits LoggedIn and stops loading`() = runTest {
        val vm = vm().apply { fill() }
        val events = mutableListOf<LoginEvent>()
        backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) { vm.events.toList(events) }

        vm.onSubmit()

        assertEquals(listOf<LoginEvent>(LoginEvent.LoggedIn), events)
        assertEquals(TEST_SESSION, storage.state.value)
        assertFalse(vm.state.value.isLoading)
        assertNull(vm.state.value.formError)
    }

    @Test fun `remember me flag is passed to the server`() {
        val vm = vm().apply { fill(); onRememberMeChange(false) }
        vm.onSubmit()
        assertFalse(repo.calls.single().rememberMe)
    }

    @Test fun `wrong credentials show form error and keep input`() {
        repo.result = LoginResult.Failure(AuthError.InvalidCredentials)
        val vm = vm().apply { fill() }
        vm.onSubmit()
        assertEquals(FormError.INVALID_CREDENTIALS, vm.state.value.formError)
        assertEquals("john@example.com", vm.state.value.email)
        assertEquals("Secret1!", vm.state.value.password)
        assertFalse(vm.state.value.isLoading)
        assertNull(storage.state.value)
    }

    @Test fun `each auth error maps to its own form error`() {
        mapOf(
            AuthError.NetworkUnavailable to FormError.NETWORK,
            AuthError.TooManyRequests(10) to FormError.TOO_MANY_REQUESTS,
            AuthError.Server to FormError.SERVER,
            AuthError.Unknown to FormError.UNKNOWN,
        ).forEach { (error, expected) ->
            repo.result = LoginResult.Failure(error)
            val vm = vm().apply { fill() }
            vm.onSubmit()
            assertEquals(expected, vm.state.value.formError)
        }
    }

    @Test fun `editing a field clears the banner and that field's error`() {
        repo.result = LoginResult.Failure(AuthError.InvalidCredentials)
        val vm = vm().apply { fill() }
        vm.onSubmit()
        vm.onPasswordChange("other")
        assertNull(vm.state.value.formError)
    }

    @Test fun `double tap while loading sends only one request`() = runTest {
        val gate = CompletableDeferred<LoginResult>()
        val slowRepo = object : com.example.vertex.domain.repository.AuthRepository {
            var count = 0
            override suspend fun login(email: String, password: String, rememberMe: Boolean): LoginResult {
                count++; return gate.await()
            }
        }
        val vm = LoginViewModel(LoginUseCase(slowRepo, storage)).apply { fill() }

        vm.onSubmit()
        assertTrue(vm.state.value.isLoading)
        vm.onSubmit()
        assertEquals(1, slowRepo.count)

        gate.complete(LoginResult.Success(TEST_SESSION))
        assertFalse(vm.state.value.isLoading)
    }

    @Test fun `password visibility toggles`() {
        val vm = vm()
        vm.onTogglePasswordVisibility(); assertTrue(vm.state.value.isPasswordVisible)
        vm.onTogglePasswordVisibility(); assertFalse(vm.state.value.isPasswordVisible)
    }
}
