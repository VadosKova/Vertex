package com.example.vertex.feature.intro

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider.AndroidViewModelFactory.Companion.APPLICATION_KEY
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.example.vertex.VertexApp
import com.example.vertex.domain.model.ThemeMode
import com.example.vertex.domain.usecase.SetThemeModeUseCase
import kotlinx.coroutines.launch

class IntroViewModel constructor(
    private val setThemeMode: SetThemeModeUseCase,
) : ViewModel() {

    fun onThemeToggleClick(isCurrentlyDark: Boolean) {
        viewModelScope.launch {
            setThemeMode(if (isCurrentlyDark) ThemeMode.LIGHT else ThemeMode.DARK)
        }
    }

    companion object {
        val Factory = viewModelFactory {
            initializer {
                val app = this[APPLICATION_KEY] as VertexApp
                IntroViewModel(app.container.setThemeMode)
            }
        }
    }
}
