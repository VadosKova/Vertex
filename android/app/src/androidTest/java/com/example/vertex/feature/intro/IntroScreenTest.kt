package com.example.vertex.feature.intro

import androidx.activity.ComponentActivity
import androidx.annotation.StringRes
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import com.example.vertex.R
import com.example.vertex.core.designsystem.theme.VertexTheme
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

class IntroScreenTest {

    @get:Rule
    val rule = createAndroidComposeRule<ComponentActivity>()

    private fun str(@StringRes id: Int) = rule.activity.getString(id)

    private var starts = 0
    private var logins = 0
    private var toggles = 0

    private fun show(isDark: Boolean = false) = rule.setContent {
        VertexTheme(darkTheme = isDark) {
            IntroScreen(
                isDarkTheme = isDark,
                onThemeToggle = { toggles++ },
                onStartClick = { starts++ },
                onLoginClick = { logins++ },
            )
        }
    }

    @Test
    fun showsAllContent() {
        show()
        rule.onNodeWithText(str(R.string.intro_title)).assertIsDisplayed()
        rule.onNodeWithText(str(R.string.intro_subtitle)).assertIsDisplayed()
        rule.onNodeWithText(str(R.string.intro_description)).assertIsDisplayed()
        rule.onNodeWithText(str(R.string.intro_start)).assertIsDisplayed()
        rule.onNodeWithText(str(R.string.intro_have_account)).assertIsDisplayed()
        rule.onNodeWithText(str(R.string.intro_login)).assertIsDisplayed()
    }

    @Test
    fun startButton_invokesCallback() {
        show()
        rule.onNodeWithText(str(R.string.intro_start)).performClick()
        assertEquals(1, starts)
        assertEquals(0, logins)
    }

    @Test
    fun loginLink_invokesCallback() {
        show()
        rule.onNodeWithText(str(R.string.intro_login)).performClick()
        assertEquals(1, logins)
        assertEquals(0, starts)
    }

    @Test
    fun lightTheme_toggleOffersDark_andInvokesCallback() {
        show(isDark = false)
        rule.onNodeWithContentDescription(str(R.string.theme_switch_to_dark)).performClick()
        assertEquals(1, toggles)
    }

    @Test
    fun darkTheme_toggleOffersLight() {
        show(isDark = true)
        rule.onNodeWithContentDescription(str(R.string.theme_switch_to_light)).assertIsDisplayed()
    }
}
