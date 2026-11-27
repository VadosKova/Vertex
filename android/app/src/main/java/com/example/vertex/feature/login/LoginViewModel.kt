package com.example.vertex.feature.login

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider.AndroidViewModelFactory.Companion.APPLICATION_KEY
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.example.vertex.VertexApp
import com.example.vertex.domain.model.LoginResult
import com.example.vertex.domain.usecase.LoginUseCase
import com.example.vertex.domain.validation.CredentialsValidator
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

class LoginViewModel(
    private val login: LoginUseCase,
) : ViewModel() {

    private val _state = MutableStateFlow(LoginUiState())
    val state: StateFlow<LoginUiState> = _state.asStateFlow()

    private val _events = Channel<LoginEvent>(Channel.BUFFERED)
    val events: Flow<LoginEvent> = _events.receiveAsFlow()

    fun onEmailChange(value: String) =
        _state.update { it.copy(email = value, emailError = null, formError = null) }

    fun onPasswordChange(value: String) =
        _state.update { it.copy(password = value, passwordError = null, formError = null) }

    fun onRememberMeChange(value: Boolean) = _state.update { it.copy(rememberMe = value) }

    fun onTogglePasswordVisibility() =
        _state.update { it.copy(isPasswordVisible = !it.isPasswordVisible) }

    fun onSubmit() {
        val current = _state.value
        if (current.isLoading) return

        val emailError = CredentialsValidator.validateEmail(current.email)
        val passwordError = CredentialsValidator.validatePassword(current.password)
        if (emailError != null || passwordError != null) {
            _state.update { it.copy(emailError = emailError, passwordError = passwordError, formError = null) }
            return
        }

        _state.update { it.copy(isLoading = true, formError = null) }
        viewModelScope.launch {
            when (val result = login(current.email, current.password, current.rememberMe)) {
                is LoginResult.Success -> {
                    _state.update { it.copy(isLoading = false) }
                    _events.send(LoginEvent.LoggedIn)
                }
                is LoginResult.Failure ->
                    _state.update { it.copy(isLoading = false, formError = result.error.toFormError()) }
            }
        }
    }

    companion object {
        val Factory = viewModelFactory {
            initializer {
                val app = this[APPLICATION_KEY] as VertexApp
                LoginViewModel(app.container.loginUseCase)
            }
        }
    }
}
