package com.example.vertex.core.designsystem.component

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import com.example.vertex.R
import com.example.vertex.core.designsystem.theme.VertexTheme


@Composable
fun ThemeToggleButton(
    isDarkTheme: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier
            .size(44.dp)
            .clip(CircleShape)
            .background(MaterialTheme.colorScheme.surface)
            .border(1.dp, VertexTheme.extraColors.borderSubtle, CircleShape)
            .clickable(role = Role.Button, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            painter = painterResource(if (isDarkTheme) R.drawable.ic_sun else R.drawable.ic_moon),
            contentDescription = stringResource(
                if (isDarkTheme) R.string.theme_switch_to_light else R.string.theme_switch_to_dark,
            ),
            tint = MaterialTheme.colorScheme.onBackground,
            modifier = Modifier.size(22.dp),
        )
    }
}
