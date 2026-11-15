package com.example.vertex.core.designsystem.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.text.ExperimentalTextApi
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import com.example.vertex.R

@OptIn(ExperimentalTextApi::class)
private fun variableFamily(resId: Int, vararg weights: FontWeight) = FontFamily(
    weights.map { w ->
        Font(
            resId = resId,
            weight = w,
            variationSettings = FontVariation.Settings(FontVariation.weight(w.weight)),
        )
    },
)

val Outfit = variableFamily(R.font.outfit_variable, FontWeight.SemiBold, FontWeight.Bold)

val Inter = variableFamily(R.font.inter_variable, FontWeight.Normal, FontWeight.Medium, FontWeight.SemiBold)

val VertexTypography = Typography(
    displayMedium = TextStyle(
        fontFamily = Outfit, fontWeight = FontWeight.Bold,
        fontSize = 36.sp, lineHeight = 44.sp, letterSpacing = 2.88.sp,
    ),

    titleMedium = TextStyle(
        fontFamily = Inter, fontWeight = FontWeight.Medium,
        fontSize = 16.sp, lineHeight = 24.sp, letterSpacing = 0.32.sp,
    ),

    bodyMedium = TextStyle(
        fontFamily = Inter, fontWeight = FontWeight.Normal,
        fontSize = 14.sp, lineHeight = 22.sp,
    ),

    labelLarge = TextStyle(
        fontFamily = Outfit, fontWeight = FontWeight.SemiBold,
        fontSize = 16.sp, lineHeight = 24.sp, letterSpacing = 1.28.sp,
    ),
)
