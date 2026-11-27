package com.example.vertex.feature.login

import androidx.activity.ComponentActivity
import androidx.annotation.StringRes
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import com.example.vertex.R
import com.example.vertex.core.designsystem.theme.VertexTheme
import com.example.vertex.domain.validation.FieldError
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

class LoginScreenTest {
    @get:Rule val rule = createAndroidComposeRule<ComponentActivity>()

    private fun str(@StringRes id: Int) = rule.activity.getString(id)

    private var email = ""; private var password = ""
    private var submits = 0; private var forgots = 0; private var registers = 0; private var toggles = 0
    private var remember: Boolean? = null

    private fun show(state: LoginUiState = LoginUiState(), dark: Boolean = false) = rule.setContent {
        VertexTheme(darkTheme = dark) {
            LoginScreen(
                state = state,
                onEmailChange = { email = it }, onPasswordChange = { password = it },
                onRememberMeChange = { remember = it },
                onTogglePasswordVisibility = { toggles++ },
                onSubmit = { submits++ },
                onForgotPasswordClick = { forgots++ }, onRegisterClick = { registers++ },
            )
        }
    }

    @Test fun showsAllElements() {
        show()
        listOf(R.string.login_title, R.string.login_subtitle, R.string.field_email, R.string.field_password,
            R.string.login_remember_me, R.string.login_button, R.string.login_forgot_password,
            R.string.login_no_account, R.string.login_register)
            .forEach { rule.onNodeWithText(str(it)).assertIsDisplayed() }
    }

    @Test fun typingReportsText() {
        show()
        rule.onNodeWithTag(LoginTestTags.EMAIL).performTextInput("john@example.com")
        rule.onNodeWithTag(LoginTestTags.PASSWORD).performTextInput("Secret1!")
        assertEquals("john@example.com", email)
        assertEquals("Secret1!", password)
    }

    @Test fun buttonsAndLinksInvokeCallbacks() {
        show()
        rule.onNodeWithText(str(R.string.login_button)).performClick()
        rule.onNodeWithText(str(R.string.login_forgot_password)).performClick()
        rule.onNodeWithText(str(R.string.login_register)).performClick()
        rule.onNodeWithContentDescription(str(R.string.password_show)).performClick()
        rule.onNodeWithText(str(R.string.login_remember_me)).performClick()
        assertEquals(1, submits); assertEquals(1, forgots); assertEquals(1, registers); assertEquals(1, toggles)
        assertEquals(false, remember)
    }

    @Test fun noBannerByDefault() {
        show()
        rule.onNodeWithText(str(R.string.error_credentials_title)).assertDoesNotExist()
    }

    @Test fun invalidCredentialsShowBanner() {
        show(LoginUiState(formError = FormError.INVALID_CREDENTIALS))
        rule.onNodeWithText(str(R.string.error_credentials_title)).assertIsDisplayed()
        rule.onNodeWithText(str(R.string.error_credentials_hint)).assertIsDisplayed()
    }

    @Test fun networkErrorShowsItsOwnBanner() {
        show(LoginUiState(formError = FormError.NETWORK), dark = true)
        rule.onNodeWithText(str(R.string.error_network_title)).assertIsDisplayed()
    }

    @Test fun fieldErrorsShowHelperText() {
        show(LoginUiState(emailError = FieldError.INVALID_EMAIL, passwordError = FieldError.EMPTY))
        rule.onNodeWithText(str(R.string.field_error_email_invalid)).assertIsDisplayed()
        rule.onNodeWithText(str(R.string.field_error_password_empty)).assertIsDisplayed()
    }

    @Test fun visiblePasswordOffersToHide() {
        show(LoginUiState(isPasswordVisible = true))
        rule.onNodeWithContentDescription(str(R.string.password_hide)).assertIsDisplayed()
    }

    @Test fun loadingButtonIgnoresClicks() {
        show(LoginUiState(isLoading = true))
        rule.onNodeWithText(str(R.string.login_button)).assertDoesNotExist()
        assertEquals(0, submits)
    }
}
