package com.example.vertex.navigation

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.example.vertex.R
import com.example.vertex.feature.intro.IntroRoute
import com.example.vertex.feature.login.LoginRoute

object Routes {
    const val INTRO = "intro"
    const val LOGIN = "login"
    const val REGISTER = "register"
    const val FORGOT = "forgot"
    const val HOME = "home"
}

@Composable
fun VertexNavHost() {
    val navController = rememberNavController()

    NavHost(navController = navController, startDestination = Routes.INTRO) {
        composable(Routes.INTRO) {
            IntroRoute(
                onStartClick = { navController.navigate(Routes.REGISTER) },
                onLoginClick = { navController.navigate(Routes.LOGIN) },
            )
        }
        composable(Routes.LOGIN) {
            LoginRoute(
                onLoggedIn = {
                    navController.navigate(Routes.HOME) {
                        popUpTo(Routes.INTRO) { inclusive = true }
                    }
                },
                onForgotPasswordClick = { navController.navigate(Routes.FORGOT) },
                onRegisterClick = { navController.navigate(Routes.REGISTER) },
            )
        }
        composable(Routes.REGISTER) { Placeholder(R.string.placeholder_register) }
        composable(Routes.FORGOT) { Placeholder(R.string.placeholder_forgot) }
        composable(Routes.HOME) { Placeholder(R.string.placeholder_home) }
    }
}

@Composable
private fun Placeholder(textRes: Int) {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Text(stringResource(textRes))
    }
}