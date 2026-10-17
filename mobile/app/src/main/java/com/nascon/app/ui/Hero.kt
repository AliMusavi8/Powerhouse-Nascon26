package com.nascon.app.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.CloudOff
import androidx.compose.material.icons.filled.Sync
import androidx.compose.material3.Icon
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.nascon.app.graph

private val OnHero = Color.White
private val HeroLine = Color.White.copy(alpha = 0.35f)

/** Diagonal stripe texture drawn over the brand colour, like a pitch. */
@Composable
fun Stripes(modifier: Modifier) {
    Canvas(modifier) {
        val step = 64.dp.toPx()
        val band = 30.dp.toPx()
        var x = -size.height
        while (x < size.width + size.height) {
            drawLine(Color.White.copy(alpha = 0.05f), Offset(x, size.height), Offset(x + size.height * 0.6f, 0f), strokeWidth = band)
            x += step
        }
    }
}

@Composable
fun CircleButton(icon: ImageVector, description: String, onClick: () -> Unit, dot: Boolean = false) {
    Box(
        Modifier.size(48.dp).clip(CircleShape).border(1.dp, HeroLine, CircleShape)
            .clickable(onClickLabel = description, role = Role.Button, onClick = onClick)
            .semantics { contentDescription = description },
        contentAlignment = Alignment.Center,
    ) {
        Icon(icon, null, tint = OnHero, modifier = Modifier.size(22.dp))
        if (dot) Box(Modifier.align(Alignment.TopEnd).padding(12.dp).size(8.dp).clip(CircleShape).background(extra.gold))
    }
}

/** Connection state as a pill in the header: Online / Offline / Syncing, always visible. */
@Composable
fun NetPill(savedAt: Long?) {
    val g = graph()
    val ui = LocalUi.current
    val online by g.network.online.collectAsStateWithLifecycle()
    val syncing by g.sync.syncing.collectAsStateWithLifecycle()
    val pending by g.db.actions().observePendingCount().collectAsStateWithLifecycle(0)
    val text = when {
        !online -> "Offline" + (if (pending > 0) " · $pending saved" else "") + (savedAt?.let { " · ${time(it)}" } ?: "")
        syncing -> "Syncing $pending"
        pending > 0 -> "Online · $pending to send"
        else -> "Online"
    }
    val bg = if (!online) extra.gold else Color.White.copy(alpha = 0.16f)
    val fg = if (!online) Color(0xFF1A1400) else OnHero
    Row(
        Modifier.heightIn(min = 32.dp).clip(RoundedCornerShape(50)).background(bg)
            .clickable(onClickLabel = "Open saved actions") { ui.nav.navigate("queue") { launchSingleTop = true } }
            .padding(horizontal = 12.dp, vertical = 6.dp)
            .semantics(mergeDescendants = true) { contentDescription = "Connection: $text. Open saved actions." },
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        when {
            !online -> Icon(Icons.Filled.CloudOff, null, tint = fg, modifier = Modifier.size(14.dp))
            syncing -> Icon(Icons.Filled.Sync, null, tint = fg, modifier = Modifier.size(14.dp))
            else -> Box(Modifier.size(7.dp).clip(CircleShape).background(if (pending > 0) extra.gold else Color(0xFF6EE7A0)))
        }
        Text(text, color = fg, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

/**
 * Screen frame: brand-coloured striped header (title, round buttons, connection pill, optional hero slot),
 * then a warm sheet with rounded top corners holding the content.
 */
@Composable
fun Page(
    title: String,
    back: Boolean = false,
    savedAt: Long? = null,
    actions: @Composable RowScope.() -> Unit = {},
    hero: (@Composable ColumnScope.() -> Unit)? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    val ui = LocalUi.current
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.primary)) {
        Box {
            Stripes(Modifier.matchParentSize())
            CompositionLocalProvider(LocalContentColor provides OnHero) {
                Column(Modifier.fillMaxWidth().statusBarsPadding().padding(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 20.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        if (back) CircleButton(Icons.AutoMirrored.Filled.ArrowBack, "Back", { ui.nav.popBackStack() })
                        else Box(
                            Modifier.size(48.dp).clip(CircleShape).background(Color.White).border(3.dp, extra.gold, CircleShape)
                                .semantics { contentDescription = "${ui.session.branding.name} logo" },
                            contentAlignment = Alignment.Center,
                        ) { Text(ui.session.branding.logoText, color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold, fontSize = 17.sp) }
                        if (back) Text(title, color = OnHero, fontSize = 16.sp, fontWeight = FontWeight.Medium, maxLines = 1,
                            overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                        else Spacer(Modifier.weight(1f))
                        NetPill(savedAt)
                        actions()
                    }
                    if (!back) Text(title, color = OnHero, fontSize = 26.sp, fontWeight = FontWeight.Bold, maxLines = 2,
                        overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 18.dp))
                    if (hero != null) Column(Modifier.padding(top = 16.dp)) { hero() }
                }
            }
        }
        Column(
            Modifier.fillMaxSize().padding(top = 0.dp).clip(SheetShape).background(MaterialTheme.colorScheme.background)
                .padding(top = 14.dp),
        ) { content() }
    }
}

/** Sheet outline: the top edge rises in a soft hump toward the middle, with rounded shoulders. */
val SheetShape = object : androidx.compose.ui.graphics.Shape {
    override fun createOutline(size: androidx.compose.ui.geometry.Size, layoutDirection: androidx.compose.ui.unit.LayoutDirection, density: androidx.compose.ui.unit.Density): androidx.compose.ui.graphics.Outline {
        val r = with(density) { 30.dp.toPx() }
        val d = with(density) { 14.dp.toPx() }
        val w = size.width
        val p = androidx.compose.ui.graphics.Path().apply {
            moveTo(0f, size.height)
            lineTo(0f, d + r)
            quadraticTo(0f, d, r, d)
            quadraticTo(w / 2f, -d, w - r, d)
            quadraticTo(w, d, w, d + r)
            lineTo(w, size.height)
            close()
        }
        return androidx.compose.ui.graphics.Outline.Generic(p)
    }
}

/** Tall outlined arrow button that sits at either end of the date strip. */
@Composable
fun ArrowPill(icon: ImageVector, description: String, enabled: Boolean, onClick: () -> Unit) {
    Box(
        Modifier.width(44.dp).height(76.dp).clip(RoundedCornerShape(22.dp)).border(1.dp, HeroLine, RoundedCornerShape(22.dp))
            .clickable(enabled = enabled, onClickLabel = description, role = Role.Button, onClick = onClick)
            .semantics { contentDescription = description },
        contentAlignment = Alignment.Center,
    ) { Icon(icon, null, tint = if (enabled) OnHero else OnHero.copy(alpha = 0.35f), modifier = Modifier.size(22.dp)) }
}

/**
 * Match card from the reference: white body with softly rounded sides, concave top and bottom edges,
 * a thin brand-coloured line drawn only along those two curves, and a badge sitting on the top line.
 */
@Composable
fun WaveCard(modifier: Modifier = Modifier, onClick: () -> Unit, badge: @Composable () -> Unit, content: @Composable ColumnScope.() -> Unit) {
    val line = MaterialTheme.colorScheme.primary.copy(alpha = 0.7f)
    val fill = MaterialTheme.colorScheme.surface
    Box(modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp)) {
        Box(
            Modifier.fillMaxWidth().padding(top = 16.dp)
                .drawBehind {
                    val r = 36.dp.toPx()
                    val d = 9.dp.toPx()
                    val w = size.width
                    val hh = size.height
                    val body = androidx.compose.ui.graphics.Path().apply {
                        moveTo(0f, r)
                        quadraticTo(0f, 0f, r, 0f)
                        quadraticTo(w / 2f, d * 2f, w - r, 0f)
                        quadraticTo(w, 0f, w, r)
                        lineTo(w, hh - r)
                        quadraticTo(w, hh, w - r, hh)
                        quadraticTo(w / 2f, hh - d * 2f, r, hh)
                        quadraticTo(0f, hh, 0f, hh - r)
                        close()
                    }
                    drawPath(body, fill)
                    val stroke = androidx.compose.ui.graphics.drawscope.Stroke(width = 1.6.dp.toPx())
                    val top = androidx.compose.ui.graphics.Path().apply {
                        moveTo(r * 0.55f, r * 0.12f); quadraticTo(r, 0f, r, 0f); quadraticTo(w / 2f, d * 2f, w - r, 0f); quadraticTo(w - r * 0.45f, 0f, w - r * 0.55f, r * 0.12f)
                    }
                    val bottom = androidx.compose.ui.graphics.Path().apply {
                        moveTo(r * 0.55f, hh - r * 0.12f); quadraticTo(r, hh, r, hh); quadraticTo(w / 2f, hh - d * 2f, w - r, hh); quadraticTo(w - r * 0.45f, hh, w - r * 0.55f, hh - r * 0.12f)
                    }
                    drawPath(top, line, style = stroke)
                    drawPath(bottom, line, style = stroke)
                }
                .clip(RoundedCornerShape(36.dp))
                .clickable(onClick = onClick),
        ) { Column(Modifier.fillMaxWidth().padding(top = 24.dp, bottom = 20.dp)) { content() } }
        Box(Modifier.align(Alignment.TopCenter)) { badge() }
    }
}

/** White day pill; the selected one is inverted (black in light mode). */
@Composable
fun DatePill(top: String, bottom: String, selected: Boolean, onClick: () -> Unit, mark: Boolean = false) {
    val bg = if (selected) extra.ink else Color.White
    val fg = if (selected) extra.onInk else Color(0xFF16171A)
    Column(
        Modifier.width(50.dp).height(76.dp).clip(RoundedCornerShape(25.dp)).background(bg)
            .clickable(onClickLabel = "Show $bottom $top", role = Role.Tab, onClick = onClick),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center,
    ) {
        Text(top, color = fg, fontSize = 18.sp, fontWeight = FontWeight.Bold)
        Text(bottom.uppercase(), color = fg, fontSize = 10.sp, letterSpacing = 0.5.sp)
        if (mark) Box(Modifier.padding(top = 3.dp).size(5.dp).clip(CircleShape).background(if (selected) extra.gold else extra.live))
    }
}

/** Black "• Live" style pill used on match cards and the match header. */
@Composable
fun BadgePill(text: String, dot: Boolean = false, inverted: Boolean = true, dotColor: Color = extra.live) {
    val bg = if (inverted) extra.ink else MaterialTheme.colorScheme.surface
    val fg = if (inverted) extra.onInk else MaterialTheme.colorScheme.onSurface
    Row(
        Modifier.clip(RoundedCornerShape(50)).background(bg)
            .let { if (!inverted) it.border(1.dp, extra.line, RoundedCornerShape(50)) else it }
            .padding(horizontal = 12.dp, vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp),
    ) {
        if (dot) Box(Modifier.size(6.dp).clip(CircleShape).background(dotColor))
        Text(text, color = fg, fontSize = 13.sp, fontWeight = FontWeight.Medium)
    }
}

/** Round crest: white disc with a soft shadow and the team initials in brand colour. */
@Composable
fun BigCrest(name: String, size: Int = 60) {
    val initials = name.split(" ").filter { it.isNotBlank() }.take(2).joinToString("") { it.take(1).uppercase() }
    Box(
        Modifier.size(size.dp).shadow(4.dp, CircleShape).clip(CircleShape).background(Color.White)
            .border(2.dp, MaterialTheme.colorScheme.primary.copy(alpha = 0.18f), CircleShape),
        contentAlignment = Alignment.Center,
    ) {
        Text(initials, color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold, fontSize = (size * 0.32).sp)
    }
}

/** Outlined pill tabs; the selected tab is filled black. */
@Composable
fun PillTabs(labels: List<String>, selected: Int, onSelect: (Int) -> Unit) {
    Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        labels.forEachIndexed { i, l ->
            val sel = i == selected
            Box(
                Modifier.weight(1f).heightIn(min = 44.dp).clip(RoundedCornerShape(50))
                    .background(if (sel) extra.ink else MaterialTheme.colorScheme.surface)
                    .border(1.dp, if (sel) extra.ink else extra.line, RoundedCornerShape(50))
                    .clickable(role = Role.Tab, onClickLabel = l) { onSelect(i) },
                contentAlignment = Alignment.Center,
            ) { Text(l, color = if (sel) extra.onInk else MaterialTheme.colorScheme.onSurface, fontSize = 14.sp, fontWeight = FontWeight.Medium) }
        }
    }
}

/** Large rounded white card used for matches and grouped content. */
/** Card outline with gently curved (concave) top and bottom edges, as on the reference match cards. */
class WaveShape(private val radius: androidx.compose.ui.unit.Dp = 30.dp, private val dip: androidx.compose.ui.unit.Dp = 12.dp) : androidx.compose.ui.graphics.Shape {
    override fun createOutline(size: androidx.compose.ui.geometry.Size, layoutDirection: androidx.compose.ui.unit.LayoutDirection, density: androidx.compose.ui.unit.Density): androidx.compose.ui.graphics.Outline {
        val r = with(density) { radius.toPx() }
        val d = with(density) { dip.toPx() }
        val w = size.width
        val hh = size.height
        val p = androidx.compose.ui.graphics.Path().apply {
            moveTo(0f, r)
            quadraticTo(0f, 0f, r, 0f)
            quadraticTo(w / 2f, d * 2f, w - r, 0f)
            quadraticTo(w, 0f, w, r)
            lineTo(w, hh - r)
            quadraticTo(w, hh, w - r, hh)
            quadraticTo(w / 2f, hh - d * 2f, r, hh)
            quadraticTo(0f, hh, 0f, hh - r)
            close()
        }
        return androidx.compose.ui.graphics.Outline.Generic(p)
    }
}

/** Turns a full-width row into a rounded white card with spacing around it. */
@Composable
fun Modifier.cardRow(): Modifier = this.padding(horizontal = 16.dp, vertical = 5.dp)
    .clip(RoundedCornerShape(22.dp)).background(MaterialTheme.colorScheme.surface)
    .border(1.dp, extra.line, RoundedCornerShape(22.dp))

/** Hairline used between rows inside one card. */
@Composable
fun CardDivider() = androidx.compose.material3.HorizontalDivider(Modifier.padding(horizontal = 16.dp), color = extra.line)

@Composable
fun BigCard(modifier: Modifier = Modifier, onClick: (() -> Unit)? = null, wave: Boolean = false, content: @Composable ColumnScope.() -> Unit) {
    Surface(
        modifier = modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
        shape = if (wave) WaveShape() else RoundedCornerShape(26.dp),
        color = MaterialTheme.colorScheme.surface,
        border = if (wave) BorderStroke(1.5.dp, MaterialTheme.colorScheme.primary.copy(alpha = 0.55f)) else BorderStroke(1.dp, extra.line),
        onClick = onClick ?: {},
        enabled = onClick != null,
    ) { Column { content() } }
}

@Composable
fun TeamBlock(name: String, modifier: Modifier = Modifier, crest: Int = 60, color: Color = MaterialTheme.colorScheme.onSurface) {
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        BigCrest(name, crest)
        Text(name, color = color, fontSize = 15.sp, textAlign = TextAlign.Center, maxLines = 2, overflow = TextOverflow.Ellipsis,
            modifier = Modifier.widthIn(max = 120.dp))
    }
}
