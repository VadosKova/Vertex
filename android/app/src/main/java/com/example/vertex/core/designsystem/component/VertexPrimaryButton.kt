package com.example.vertex.core.designsystem.component

import android.graphics.Color as AndroidColor
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Paint
import androidx.compose.ui.graphics.drawscope.drawIntoCanvas
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.example.vertex.core.designsystem.theme.VertexTheme


@Composable
fun VertexPrimaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val interactionSource = remember { MutableInteractionSource() }
    val pressed by interactionSource.collectIsPressedAsState()
    val shape = RoundedCornerShape(28.dp)
    val extra = VertexTheme.extraColors

    Box(
        modifier = modifier
            .height(56.dp)
            .dropShadow(
                color = extra.buttonShadow,
                offsetY = 8.dp,
                blur = 12.dp,
                cornerRadius = 28.dp,
            )
            .clip(shape)
            .background(if (pressed) extra.primaryVariant else MaterialTheme.colorScheme.primary)
            .clickable(
                interactionSource = interactionSource,
                indication = null,
                role = Role.Button,
                onClick = onClick,
            )
            .padding(horizontal = 24.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = text,
            style = MaterialTheme.typography.labelLarge,
            color = MaterialTheme.colorScheme.onPrimary,
        )
    }
}

private fun Modifier.dropShadow(
    color: Color,
    offsetY: Dp,
    blur: Dp,
    cornerRadius: Dp,
): Modifier = drawBehind {
    drawIntoCanvas { canvas ->
        val paint = Paint()
        paint.asFrameworkPaint().apply {
            isAntiAlias = true
            this.color = AndroidColor.TRANSPARENT
            setShadowLayer(blur.toPx(), 0f, offsetY.toPx(), color.toArgb())
        }
        val radius = cornerRadius.toPx()
        canvas.nativeCanvas.drawRoundRect(0f, 0f, size.width, size.height, radius, radius, paint.asFrameworkPaint())
    }
}