package com.nascon.app.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import com.nascon.app.data.Branding

@Immutable
data class Extra(
    val link: Color,
    val tint: Color,
    val live: Color,
    val ok: Color,
    val okBg: Color,
    val bad: Color,
    val badBg: Color,
    val warn: Color,
    val warnBg: Color,
    val gold: Color,
    val muted: Color,
    val line: Color,
)

val LocalExtra = staticCompositionLocalOf {
    Extra(Color.Blue, Color.LightGray, Color.Red, Color.Green, Color.White, Color.Red, Color.White, Color.Yellow, Color.White, Color.Yellow, Color.Gray, Color.LightGray)
}

val Numbers = FontFamily.SansSerif
private val Condensed = FontFamily(android.graphics.Typeface.create("sans-serif-condensed", android.graphics.Typeface.NORMAL))

val ScoreStyle = TextStyle(fontFamily = Condensed, fontWeight = FontWeight.SemiBold, fontSize = 44.sp, lineHeight = 46.sp)
val NumStyle = TextStyle(fontFamily = Condensed, fontWeight = FontWeight.Medium, fontSize = 15.sp)

@Composable
fun AppTheme(branding: Branding?, content: @Composable () -> Unit) {
    val primary = branding?.primary ?: Color(0xFF1E4FD8)
    val gold = branding?.secondary ?: Color(0xFFF5B700)
    val dark = isSystemInDarkTheme()
    val scheme = if (dark) darkColorScheme(
        primary = primary, onPrimary = Color.White,
        secondary = gold, onSecondary = Color(0xFF1A1400),
        background = Color(0xFF0E0F11), onBackground = Color(0xFFECEDEF),
        surface = Color(0xFF17181B), onSurface = Color(0xFFECEDEF),
        surfaceVariant = Color(0xFF202125), onSurfaceVariant = Color(0xFF999CA4),
        surfaceContainer = Color(0xFF17181B), surfaceContainerHigh = Color(0xFF202125),
        surfaceContainerLow = Color(0xFF141518), surfaceContainerLowest = Color(0xFF0E0F11),
        surfaceContainerHighest = Color(0xFF26272C),
        outline = Color(0xFF3A3B41), outlineVariant = Color(0xFF2A2B30),
        error = Color(0xFFF7766C), onError = Color(0xFF1F0705),
        primaryContainer = Color(0xFF18223F), onPrimaryContainer = Color(0xFFC9D6FF),
        secondaryContainer = Color(0xFF202125), onSecondaryContainer = Color(0xFFECEDEF),
    ) else lightColorScheme(
        primary = primary, onPrimary = Color.White,
        secondary = gold, onSecondary = Color(0xFF1A1400),
        background = Color(0xFFF4F4F5), onBackground = Color(0xFF16171A),
        surface = Color.White, onSurface = Color(0xFF16171A),
        surfaceVariant = Color(0xFFF1F2F4), onSurfaceVariant = Color(0xFF6A6D75),
        surfaceContainer = Color.White, surfaceContainerHigh = Color(0xFFF1F2F4),
        surfaceContainerLow = Color(0xFFF8F8F9), surfaceContainerLowest = Color.White,
        surfaceContainerHighest = Color(0xFFE9EAED),
        outline = Color(0xFFC9CBD1), outlineVariant = Color(0xFFE5E6E9),
        error = Color(0xFFB42318), onError = Color.White,
        primaryContainer = Color(0xFFEAF0FD), onPrimaryContainer = Color(0xFF0D2A85),
        secondaryContainer = Color(0xFFF1F2F4), onSecondaryContainer = Color(0xFF16171A),
    )
    val extra = if (dark) Extra(
        link = Color(0xFF7299FF), tint = Color(0xFF18223F), live = Color(0xFFFF5C55),
        ok = Color(0xFF52C48D), okBg = Color(0xFF13271D), bad = Color(0xFFF7766C), badBg = Color(0xFF2C1715),
        warn = Color(0xFFF2C14E), warnBg = Color(0xFF2A2312), gold = gold, muted = Color(0xFF999CA4), line = Color(0xFF2A2B30),
    ) else Extra(
        link = primary, tint = Color(0xFFEAF0FD), live = Color(0xFFD12C2C),
        ok = Color(0xFF1C7A44), okBg = Color(0xFFE6F3EB), bad = Color(0xFFB42318), badBg = Color(0xFFFCEBE9),
        warn = Color(0xFF7A5300), warnBg = Color(0xFFFFF3D1), gold = gold, muted = Color(0xFF6A6D75), line = Color(0xFFE5E6E9),
    )
    val base = Typography()
    val type = base.copy(
        titleLarge = base.titleLarge.copy(fontSize = 20.sp, fontWeight = FontWeight.Medium),
        titleMedium = base.titleMedium.copy(fontSize = 16.sp, fontWeight = FontWeight.Medium),
        labelSmall = base.labelSmall.copy(fontSize = 11.sp, letterSpacing = 0.8.sp, fontWeight = FontWeight.Medium),
    )
    CompositionLocalProvider(LocalExtra provides extra) {
        MaterialTheme(colorScheme = scheme, typography = type, content = content)
    }
}
