package com.example.vertex.feature.login

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.example.vertex.R
import com.example.vertex.core.designsystem.component.ErrorBanner
import com.example.vertex.core.designsystem.component.VertexCheckbox
import com.example.vertex.core.designsystem.component.VertexPrimaryButton
import com.example.vertex.core.designsystem.component.VertexTextField
import com.example.vertex.core.designsystem.theme.VertexTheme
import com.example.vertex.domain.validation.FieldError

object LoginTestTags {
    const val EMAIL = "login_email"
    const val PASSWORD = "login_password"
}

@Composable
fun LoginRoute(
    onLoggedIn: () -> Unit,
    onForgotPasswordClick: () -> Unit,
    onRegisterClick: () -> Unit,
    viewModel: LoginViewModel = viewModel(factory = LoginViewModel.Factory),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    LaunchedEffect(viewModel) {
        viewModel.events.collect { event ->
            when (event) {
                LoginEvent.LoggedIn -> onLoggedIn()
            }
        }
    }

    LoginScreen(
        state = state,
        onEmailChange = viewModel::onEmailChange,
        onPasswordChange = viewModel::onPasswordChange,
        onRememberMeChange = viewModel::onRememberMeChange,
        onTogglePasswordVisibility = viewModel::onTogglePasswordVisibility,
        onSubmit = viewModel::onSubmit,
        onForgotPasswordClick = onForgotPasswordClick,
        onRegisterClick = onRegisterClick,
    )
}

@Composable
fun LoginScreen(
    state: LoginUiState,
    onEmailChange: (String) -> Unit,
    onPasswordChange: (String) -> Unit,
    onRememberMeChange: (Boolean) -> Unit,
    onTogglePasswordVisibility: () -> Unit,
    onSubmit: () -> Unit,
    onForgotPasswordClick: () -> Unit,
    onRegisterClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val glow = VertexTheme.extraColors.screenGlow
    val focusManager = LocalFocusManager.current

    Box(
        modifier = modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .drawBehind {
                drawCircle(
                    brush = Brush.radialGradient(
                        colors = listOf(glow, Color.Transparent),
                        center = Offset(size.width - 106.dp.toPx(), 0f),
                        radius = 190.dp.toPx(),
                    ),
                    radius = 190.dp.toPx(),
                    center = Offset(size.width - 106.dp.toPx(), 0f),
                )
            },
    ) {
        BoxWithConstraints(
            modifier = Modifier
                .fillMaxSize()
                .safeDrawingPadding()
                .imePadding(),
        ) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
                    .heightIn(min = maxHeight)
                    .padding(start = 24.dp, end = 24.dp, top = 56.dp, bottom = 18.dp),
                verticalArrangement = Arrangement.spacedBy(32.dp),
            ) {
                Header()
                Form(
                    state = state,
                    onEmailChange = onEmailChange,
                    onPasswordChange = onPasswordChange,
                    onRememberMeChange = onRememberMeChange,
                    onTogglePasswordVisibility = onTogglePasswordVisibility,
                    onSubmit = { focusManager.clearFocus(); onSubmit() },
                    onForgotPasswordClick = onForgotPasswordClick,
                )
                Spacer(Modifier.weight(1f))
                RegisterFooter(onRegisterClick = onRegisterClick)
            }
        }
    }
}

@Composable
private fun Header() {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(
            text = stringResource(R.string.login_title),
            style = MaterialTheme.typography.headlineMedium,
            color = MaterialTheme.colorScheme.onBackground,
            modifier = Modifier.semantics { heading() },
        )
        Text(
            text = stringResource(R.string.login_subtitle),
            style = MaterialTheme.typography.bodyMedium.copy(lineHeight = 20.sp),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun Form(
    state: LoginUiState,
    onEmailChange: (String) -> Unit,
    onPasswordChange: (String) -> Unit,
    onRememberMeChange: (Boolean) -> Unit,
    onTogglePasswordVisibility: () -> Unit,
    onSubmit: () -> Unit,
    onForgotPasswordClick: () -> Unit,
) {
    val credentialsRejected = state.formError == FormError.INVALID_CREDENTIALS

    Column {
        state.formError?.let { error ->
            val (title, hint) = error.texts()
            ErrorBanner(title = title, message = hint)
            Spacer(Modifier.height(20.dp))
        }

        VertexTextField(
            label = stringResource(R.string.field_email),
            value = state.email,
            onValueChange = onEmailChange,
            modifier = Modifier.testTag(LoginTestTags.EMAIL),
            errorText = state.emailError?.let { emailErrorText(it) },
            forceError = credentialsRejected,
            enabled = !state.isLoading,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email, imeAction = ImeAction.Next),
        )

        Spacer(Modifier.height(20.dp))

        VertexTextField(
            label = stringResource(R.string.field_password),
            value = state.password,
            onValueChange = onPasswordChange,
            modifier = Modifier.testTag(LoginTestTags.PASSWORD),
            errorText = state.passwordError?.let { stringResource(R.string.field_error_password_empty) },
            forceError = credentialsRejected,
            enabled = !state.isLoading,
            visualTransformation = if (state.isPasswordVisible) VisualTransformation.None
            else PasswordVisualTransformation('•'),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Done),
            keyboardActions = KeyboardActions(onDone = { onSubmit() }),
            trailingContent = {
                Icon(
                    painter = painterResource(if (state.isPasswordVisible) R.drawable.ic_eye_off else R.drawable.ic_eye),
                    contentDescription = stringResource(
                        if (state.isPasswordVisible) R.string.password_hide else R.string.password_show,
                    ),
                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier
                        .size(20.dp)
                        .clickable(role = Role.Button, onClick = onTogglePasswordVisibility),
                )
            },
        )

        Spacer(Modifier.height(7.dp))

        VertexCheckbox(
            checked = state.rememberMe,
            onCheckedChange = onRememberMeChange,
            label = stringResource(R.string.login_remember_me),
        )

        Spacer(Modifier.height(7.dp))

        VertexPrimaryButton(
            text = stringResource(R.string.login_button),
            onClick = onSubmit,
            isLoading = state.isLoading,
            modifier = Modifier.fillMaxWidth(),
        )

        Spacer(Modifier.height(6.dp))

        Text(
            text = stringResource(R.string.login_forgot_password),
            style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Medium, lineHeight = 20.sp),
            color = MaterialTheme.colorScheme.primary,
            textAlign = TextAlign.Center,
            modifier = Modifier
                .fillMaxWidth()
                .clickable(role = Role.Button, onClick = onForgotPasswordClick)
                .padding(vertical = 14.dp),
        )
    }
}

@Composable
private fun RegisterFooter(onRegisterClick: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = stringResource(R.string.login_no_account),
            style = MaterialTheme.typography.bodyMedium.copy(lineHeight = 20.sp),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(vertical = 14.dp),
        )
        Spacer(Modifier.width(4.dp))
        Text(
            text = stringResource(R.string.login_register),
            style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.SemiBold, lineHeight = 20.sp),
            color = MaterialTheme.colorScheme.primary,
            modifier = Modifier
                .clickable(role = Role.Button, onClick = onRegisterClick)
                .padding(vertical = 14.dp),
        )
    }
}

@Composable
private fun emailErrorText(error: FieldError): String = stringResource(
    if (error == FieldError.EMPTY) R.string.field_error_email_empty else R.string.field_error_email_invalid,
)

@Composable
private fun FormError.texts(): Pair<String, String> = when (this) {
    FormError.INVALID_CREDENTIALS ->
        stringResource(R.string.error_credentials_title) to stringResource(R.string.error_credentials_hint)
    FormError.NETWORK ->
        stringResource(R.string.error_network_title) to stringResource(R.string.error_network_hint)
    FormError.TOO_MANY_REQUESTS ->
        stringResource(R.string.error_too_many_title) to stringResource(R.string.error_too_many_hint)
    FormError.SERVER ->
        stringResource(R.string.error_server_title) to stringResource(R.string.error_server_hint)
    FormError.UNKNOWN ->
        stringResource(R.string.error_unknown_title) to stringResource(R.string.error_unknown_hint)
}

@Preview(showBackground = true, widthDp = 412, heightDp = 917, name = "Login / Light")
@Composable
private fun LoginLightPreview() = VertexTheme(darkTheme = false) {
    LoginScreen(
        state = LoginUiState(email = "john.doe@example.com", password = "password123!"),
        onEmailChange = {}, onPasswordChange = {}, onRememberMeChange = {}, onTogglePasswordVisibility = {},
        onSubmit = {}, onForgotPasswordClick = {}, onRegisterClick = {},
    )
}

@Preview(showBackground = true, widthDp = 412, heightDp = 917, name = "Login Error / Dark")
@Composable
private fun LoginErrorDarkPreview() = VertexTheme(darkTheme = true) {
    LoginScreen(
        state = LoginUiState(
            email = "john.doe@example.com", password = "password123!", formError = FormError.INVALID_CREDENTIALS,
        ),
        onEmailChange = {}, onPasswordChange = {}, onRememberMeChange = {}, onTogglePasswordVisibility = {},
        onSubmit = {}, onForgotPasswordClick = {}, onRegisterClick = {},
    )
}
