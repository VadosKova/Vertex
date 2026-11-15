package com.example.vertex.feature.intro

import com.example.vertex.domain.model.ThemeMode
import com.example.vertex.domain.usecase.SetThemeModeUseCase
import com.example.vertex.testutil.FakeSettingsRepository
import com.example.vertex.testutil.MainDispatcherRule
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

class IntroViewModelTest {

    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    private val repository = FakeSettingsRepository(ThemeMode.LIGHT)
    private val viewModel = IntroViewModel(SetThemeModeUseCase(repository))

    @Test
    fun `toggle from light stores DARK`() {
        viewModel.onThemeToggleClick(isCurrentlyDark = false)
        assertEquals(ThemeMode.DARK, repository.state.value)
    }

    @Test
    fun `toggle from dark stores LIGHT`() {
        viewModel.onThemeToggleClick(isCurrentlyDark = true)
        assertEquals(ThemeMode.LIGHT, repository.state.value)
    }

    @Test
    fun `toggle uses what the user sees even when stored mode is SYSTEM`() {
        repository.state.value = ThemeMode.SYSTEM
        viewModel.onThemeToggleClick(isCurrentlyDark = true)
        assertEquals(ThemeMode.LIGHT, repository.state.value)
    }

    @Test
    fun `double toggle returns to the original theme`() {
        viewModel.onThemeToggleClick(isCurrentlyDark = false)
        viewModel.onThemeToggleClick(isCurrentlyDark = true)
        assertEquals(ThemeMode.LIGHT, repository.state.value)
    }
}
