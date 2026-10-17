package com.nascon.app.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.size
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
fun ScorixLogo(size: Int = 48, corner: Int = 14) {
    Image(
        painterResource(R.drawable.scorix_logo), contentDescription = "Scorix logo",
        contentScale = ContentScale.Crop,
        modifier = Modifier.size(size.dp).clip(RoundedCornerShape(corner.dp)),
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
        Box(
            Modifier.align(Alignment.BottomEnd).size((size * 0.36).dp).clip(CircleShape).background(Color(0xFF111111))
                .border(2.dp, Color.White, CircleShape),
            contentAlignment = Alignment.Center,
        ) { Text(initials(name), color = Color.White, fontWeight = FontWeight.Bold, fontSize = (size * 0.13).sp) }
    }
}
