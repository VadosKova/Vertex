package com.example.vertex

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider.AndroidViewModelFactory.Companion.APPLICATION_KEY
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.example.vertex.domain.model.ThemeMode
import com.example.vertex.domain.usecase.ObserveThemeModeUseCase
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn


class MainViewModel(
    observeThemeMode: ObserveThemeModeUseCase,
) : ViewModel() {

    val themeMode: StateFlow<ThemeMode?> = observeThemeMode()
        .stateIn(
            scope = viewModelScope,
            started = SharingStarted.Eagerly,
            initialValue = null,
        )

    companion object {
        val Factory = viewModelFactory {
            initializer {
                val app = this[APPLICATION_KEY] as VertexApp
                MainViewModel(app.container.observeThemeMode)
            }
        }
    }
}
