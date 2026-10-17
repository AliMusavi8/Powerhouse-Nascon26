package com.nascon.app.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.nascon.app.R

/** Kit colour pairs; each club gets a stable pair from its name. */
private val kits = listOf(
    Color(0xFF1C8B2E) to Color(0xFFF5F2E6),
    Color(0xFF1E4FD8) to Color(0xFFF5B700),
    Color(0xFFC8102E) to Color(0xFFFFFFFF),
    Color(0xFF6A1B9A) to Color(0xFFFFD54F),
    Color(0xFF0B1F3A) to Color(0xFF4FC3F7),
    Color(0xFFE65100) to Color(0xFF1A1A1A),
    Color(0xFF00695C) to Color(0xFFFFFFFF),
    Color(0xFF263238) to Color(0xFFCDDC39),
)

private fun kitFor(name: String) = kits[Math.floorMod(name.hashCode(), kits.size)]

private fun initials(name: String) =
    name.split(" ").filter { it.isNotBlank() }.take(2).joinToString("") { it.take(1).uppercase() }.ifBlank { "?" }

@Composable
fun ScorixLogo(size: Int = 48, corner: Int = 14, circle: Boolean = false) {
    Image(
        painterResource(R.drawable.scorix_logo), contentDescription = "Scorix logo",
        contentScale = ContentScale.Crop,
        modifier = Modifier.size(size.dp).clip(if (circle) CircleShape else RoundedCornerShape(corner.dp)),
    )
}

/** Club badge drawn as a shield in the club's kit colours, with a diagonal sash and initials. */
@Composable
fun ClubBadge(name: String, size: Int = 56) {
    val (main, accent) = kitFor(name)
    Box(
        Modifier.size(size.dp).shadow(3.dp, CircleShape).clip(CircleShape).background(Color.White)
            .border(1.dp, Color(0x1F000000), CircleShape)
            .semantics { contentDescription = "$name badge" },
        contentAlignment = Alignment.Center,
    ) {
        Canvas(Modifier.size((size * 0.72).dp)) {
            val w = this.size.width
            val h = this.size.height
            val shield = Path().apply {
                moveTo(w * 0.5f, 0f)
                lineTo(w, h * 0.14f)
                lineTo(w * 0.94f, h * 0.62f)
                quadraticTo(w * 0.82f, h * 0.88f, w * 0.5f, h)
                quadraticTo(w * 0.18f, h * 0.88f, w * 0.06f, h * 0.62f)
                lineTo(0f, h * 0.14f)
                close()
            }
            drawPath(shield, main)
            drawLine(accent, Offset(w * 0.08f, h * 0.92f), Offset(w * 0.92f, h * 0.1f), strokeWidth = w * 0.16f)
            drawPath(shield, accent, style = Stroke(width = w * 0.06f))
        }
        Box(
            Modifier.size((size * 0.36).dp).clip(CircleShape).background(Color.White.copy(alpha = 0.92f)),
            contentAlignment = Alignment.Center,
        ) { Text(initials(name), color = main, fontWeight = FontWeight.Black, fontSize = (size * 0.15).sp) }
    }
}

/** Profile picture: soft gradient disc with a person silhouette and initials badge. */
@Composable
fun Avatar(name: String, size: Int = 64) {
    val (main, accent) = kitFor(name + "#p")
    Box(Modifier.size(size.dp).semantics { contentDescription = "Profile picture of $name" }) {
        Canvas(Modifier.fillMaxSize().clip(CircleShape)
            .background(Brush.linearGradient(listOf(main, main.copy(alpha = 0.75f), accent.copy(alpha = 0.9f))))) {
            val w = this.size.width
            val h = this.size.height
            drawCircle(Color.White.copy(alpha = 0.92f), radius = w * 0.18f, center = Offset(w / 2f, h * 0.38f))
            drawOval(Color.White.copy(alpha = 0.92f), topLeft = Offset(w * 0.2f, h * 0.62f), size = androidx.compose.ui.geometry.Size(w * 0.6f, h * 0.5f))
        }
    }
}

/**
 * Product picture drawn from the product's category and name, in kit colours.
 * Shapes: shirt (default apparel), cap, scarf, and a phone screen for digital items.
 */
@Composable
fun ProductArt(product: kotlinx.serialization.json.JsonObject?, modifier: Modifier = Modifier) {
    val name = (product?.get("name") as? kotlinx.serialization.json.JsonPrimitive)?.content ?: ""
    val category = (product?.get("category") as? kotlinx.serialization.json.JsonPrimitive)?.content ?: ""
    val (main, accent) = kitFor(name)
    val n = name.lowercase()
    val kind = when {
        category.contains("digital", true) -> 3
        n.contains("cap") || n.contains("hat") -> 1
        n.contains("scarf") -> 2
        else -> 0
    }
    Box(
        modifier.background(Brush.linearGradient(listOf(main.copy(alpha = 0.16f), accent.copy(alpha = 0.28f))))
            .semantics { contentDescription = "Picture of $name" },
        contentAlignment = Alignment.Center,
    ) {
        Canvas(Modifier.fillMaxSize(0.72f)) {
            val w = this.size.width
            val h = this.size.height
            val s = minOf(w, h)
            val ox = (w - s) / 2f
            val oy = (h - s) / 2f
            fun p(x: Float, y: Float) = Offset(ox + x * s, oy + y * s)
            when (kind) {
                0 -> { // shirt
                    val shirt = Path().apply {
                        moveTo(p(0.35f, 0.08f).x, p(0.35f, 0.08f).y)
                        quadraticTo(p(0.5f, 0.2f).x, p(0.5f, 0.2f).y, p(0.65f, 0.08f).x, p(0.65f, 0.08f).y)
                        lineTo(p(0.95f, 0.22f).x, p(0.95f, 0.22f).y); lineTo(p(0.85f, 0.42f).x, p(0.85f, 0.42f).y)
                        lineTo(p(0.75f, 0.37f).x, p(0.75f, 0.37f).y); lineTo(p(0.75f, 0.95f).x, p(0.75f, 0.95f).y)
                        lineTo(p(0.25f, 0.95f).x, p(0.25f, 0.95f).y); lineTo(p(0.25f, 0.37f).x, p(0.25f, 0.37f).y)
                        lineTo(p(0.15f, 0.42f).x, p(0.15f, 0.42f).y); lineTo(p(0.05f, 0.22f).x, p(0.05f, 0.22f).y); close()
                    }
                    drawPath(shirt, main)
                    drawLine(accent, p(0.42f, 0.2f), p(0.42f, 0.95f), strokeWidth = s * 0.05f)
                    drawLine(accent, p(0.58f, 0.2f), p(0.58f, 0.95f), strokeWidth = s * 0.05f)
                    drawPath(shirt, Color.Black.copy(alpha = 0.15f), style = Stroke(width = s * 0.015f))
                }
                1 -> { // cap
                    drawArc(main, 180f, 180f, true, p(0.14f, 0.2f), androidx.compose.ui.geometry.Size(s * 0.72f, s * 0.72f))
                    drawRoundRect(accent, p(0.42f, 0.5f), androidx.compose.ui.geometry.Size(s * 0.52f, s * 0.1f), androidx.compose.ui.geometry.CornerRadius(s * 0.05f))
                    drawCircle(accent, s * 0.04f, p(0.5f, 0.2f))
                    drawLine(accent, p(0.5f, 0.22f), p(0.5f, 0.55f), strokeWidth = s * 0.02f)
                }
                2 -> { // scarf
                    for (i in 0 until 6) {
                        val c = if (i % 2 == 0) main else accent
                        drawRect(c, p(0.06f + i * 0.148f, 0.36f), androidx.compose.ui.geometry.Size(s * 0.149f, s * 0.26f))
                    }
                    for (i in 0 until 8) {
                        drawLine(main, p(0.08f + i * 0.12f, 0.62f), p(0.08f + i * 0.12f, 0.72f), strokeWidth = s * 0.02f)
                        drawLine(main, p(0.08f + i * 0.12f, 0.36f), p(0.08f + i * 0.12f, 0.26f), strokeWidth = s * 0.02f)
                    }
                }
                else -> { // phone wallpaper
                    drawRoundRect(Color(0xFF111111), p(0.28f, 0.04f), androidx.compose.ui.geometry.Size(s * 0.44f, s * 0.92f), androidx.compose.ui.geometry.CornerRadius(s * 0.07f))
                    drawRoundRect(Brush.linearGradient(listOf(main, accent), p(0.31f, 0.08f), p(0.69f, 0.92f)), p(0.31f, 0.08f),
                        androidx.compose.ui.geometry.Size(s * 0.38f, s * 0.84f), androidx.compose.ui.geometry.CornerRadius(s * 0.05f))
                    drawCircle(Color.White.copy(alpha = 0.85f), s * 0.08f, p(0.5f, 0.45f))
                }
            }
        }
    }
}

/** Launch screen: brand green with pitch stripes, the round logo and the app name. */
@Composable
fun SplashScreen() {
    Box(
        Modifier.fillMaxSize().background(androidx.compose.material3.MaterialTheme.colorScheme.primary),
        contentAlignment = Alignment.Center,
    ) {
        Stripes(Modifier.fillMaxSize())
        androidx.compose.foundation.layout.Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Box(Modifier.shadow(16.dp, CircleShape).border(3.dp, Color.White.copy(alpha = 0.8f), CircleShape)) { ScorixLogo(132, circle = true) }
            Text("Scorix", color = Color.White, fontSize = 40.sp, fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(top = 20.dp))
            Text("Live scores · Standings · Clubs · Store", color = Color.White.copy(alpha = 0.8f), fontSize = 14.sp)
        }
    }
}
