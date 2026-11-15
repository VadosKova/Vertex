package com.example.vertex.feature.intro

import androidx.compose.foundation.Image
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
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.requiredSize
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.example.vertex.R
import com.example.vertex.core.designsystem.component.ThemeToggleButton
import com.example.vertex.core.designsystem.component.VertexPrimaryButton
import com.example.vertex.core.designsystem.theme.VertexTheme


@Composable
fun IntroRoute(
    onStartClick: () -> Unit,
    onLoginClick: () -> Unit,
    viewModel: IntroViewModel = viewModel(factory = IntroViewModel.Factory),
) {
    val isDark = VertexTheme.isDark
    IntroScreen(
        isDarkTheme = isDark,
        onThemeToggle = { viewModel.onThemeToggleClick(isCurrentlyDark = isDark) },
        onStartClick = onStartClick,
        onLoginClick = onLoginClick,
    )
}

@Composable
fun IntroScreen(
    isDarkTheme: Boolean,
    onThemeToggle: () -> Unit,
    onStartClick: () -> Unit,
    onLoginClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background),
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .safeDrawingPadding()
                .padding(start = 24.dp, end = 24.dp, top = 16.dp, bottom = 24.dp),
        ) {
            BoxWithConstraints(modifier = Modifier.weight(1f).fillMaxWidth()) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .verticalScroll(rememberScrollState())
                        .heightIn(min = maxHeight),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center,
                ) {
                    LogoWithGlow()
                    Spacer(Modifier.height(28.dp))
                    TitleBlock()
                    Spacer(Modifier.height(28.dp))
                    Text(
                        text = stringResource(R.string.intro_description),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onBackground,
                        textAlign = TextAlign.Center,
                    )
                }
            }

            Footer(onStartClick = onStartClick, onLoginClick = onLoginClick)
        }

        ThemeToggleButton(
            isDarkTheme = isDarkTheme,
            onClick = onThemeToggle,
            modifier = Modifier
                .align(Alignment.TopEnd)
                .safeDrawingPadding()
                .padding(top = 12.dp, end = 24.dp),
        )
    }
}

@Composable
private fun LogoWithGlow() {
    Box(contentAlignment = Alignment.Center, modifier = Modifier.size(width = 141.dp, height = 142.dp)) {
        Box(
            modifier = Modifier
                .requiredSize(320.dp)
                .background(
                    Brush.radialGradient(
                        colors = listOf(VertexTheme.extraColors.logoGlow, Color.Transparent),
                    ),
                ),
        )
        Image(
            painter = painterResource(R.drawable.vertex_logo),
            contentDescription = null,
            modifier = Modifier.fillMaxSize(),
        )
    }
}

@Composable
private fun TitleBlock() {
    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(
            text = stringResource(R.string.intro_title),
            style = MaterialTheme.typography.displayMedium,
            color = MaterialTheme.colorScheme.onBackground,
            modifier = Modifier.semantics { heading() },
        )
        Text(
            text = stringResource(R.string.intro_subtitle),
            style = MaterialTheme.typography.titleMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun Footer(onStartClick: () -> Unit, onLoginClick: () -> Unit) {
    Column(modifier = Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
        VertexPrimaryButton(
            text = stringResource(R.string.intro_start),
            onClick = onStartClick,
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(6.dp))
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.Center,
            modifier = Modifier.padding(vertical = 14.dp),
        ) {
            Text(
                text = stringResource(R.string.intro_have_account),
                style = MaterialTheme.typography.bodyMedium.copy(lineHeight = 20.sp),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.width(4.dp))
            Text(
                text = stringResource(R.string.intro_login),
                style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.SemiBold),
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.clickable(role = Role.Button, onClick = onLoginClick),
            )
        }
    }
}

@Preview(showBackground = true, widthDp = 412, heightDp = 917, name = "Intro / Light")
@Composable
private fun IntroLightPreview() = VertexTheme(darkTheme = false) {
    IntroScreen(isDarkTheme = false, onThemeToggle = {}, onStartClick = {}, onLoginClick = {})
}

@Preview(showBackground = true, widthDp = 412, heightDp = 917, name = "Intro / Dark")
@Composable
private fun IntroDarkPreview() = VertexTheme(darkTheme = true) {
    IntroScreen(isDarkTheme = true, onThemeToggle = {}, onStartClick = {}, onLoginClick = {})
}

@Preview(showBackground = true, widthDp = 320, heightDp = 480, fontScale = 1.5f, name = "Intro / small + big font")
@Composable
private fun IntroSmallPreview() = VertexTheme(darkTheme = false) {
    IntroScreen(isDarkTheme = false, onThemeToggle = {}, onStartClick = {}, onLoginClick = {})
}
