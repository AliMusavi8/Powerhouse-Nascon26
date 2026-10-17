package com.nascon.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.draw.clip
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.TableRows
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.VerticalDivider
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.nascon.app.data.arr
import com.nascon.app.data.int
import com.nascon.app.data.obj
import com.nascon.app.data.str
import kotlinx.serialization.json.JsonObject
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

/** League choices shown in the dropdown under the header logo. */
@Composable
fun LeagueMenuItems(leagues: List<Pair<String, String>>, dismiss: () -> Unit) {
    val league = LocalLeague.current
    Text("League", style = MaterialTheme.typography.labelSmall, color = extra.muted, modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp))
    if (leagues.isEmpty()) Text("No leagues available", color = extra.muted, modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp))
    leagues.forEach { (id, name) ->
        androidx.compose.material3.DropdownMenuItem(
            text = { Text(name, fontWeight = if (league.leagueId == id) FontWeight.Bold else FontWeight.Normal) },
            leadingIcon = {
                if (league.leagueId == id) androidx.compose.material3.Icon(Icons.Filled.Check, contentDescription = "Selected", tint = MaterialTheme.colorScheme.primary)
                else Box(Modifier.width(24.dp))
            },
            onClick = { league.leagueId = id; dismiss() },
            modifier = Modifier.heightIn(min = 48.dp),
        )
    }
}

private val inFmt = DateTimeFormatter.ISO_OFFSET_DATE_TIME
fun parseTime(s: String?): OffsetDateTime? = try { s?.let { OffsetDateTime.parse(it.replace("Z", "+00:00"), inFmt) } } catch (e: Exception) { null }
fun dayLabel(t: OffsetDateTime?) = t?.atZoneSameInstant(ZoneId.systemDefault())?.format(DateTimeFormatter.ofPattern("EEE d MMM", Locale.getDefault())) ?: "Date to be confirmed"
fun clock(t: OffsetDateTime?) = t?.atZoneSameInstant(ZoneId.systemDefault())?.format(DateTimeFormatter.ofPattern("HH:mm")) ?: "TBC"

fun dayKey(t: OffsetDateTime?) = t?.atZoneSameInstant(ZoneId.systemDefault())?.toLocalDate()?.toString() ?: "tbc"

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FixturesScreen() {
    val ui = LocalUi.current
    val leagues = rememberLeagues()
    val league = LocalLeague.current
    val res = rememberRes(league.leagueId?.let { "/api/v1/leagues/$it/fixtures" })
    val fixtures = res.loaded?.data?.arr("fixtures")?.sortedBy { it.str("scheduled_at") ?: "" } ?: emptyList()
    val days = fixtures.map { dayKey(parseTime(it.str("scheduled_at"))) }.distinct()
    val today = java.time.LocalDate.now().toString()
    var picked by rememberSaveable(league.leagueId) { mutableStateOf<String?>(null) }
    val day = picked?.takeIf { it in days } ?: days.firstOrNull { it >= today } ?: days.lastOrNull()
    val dayState = rememberLazyListState()
    LaunchedEffect(days.size) { days.indexOf(day).takeIf { it > 1 }?.let { dayState.scrollToItem(it - 1) } }

    Page(
        "Scores & Fixtures", savedAt = res.loaded?.savedAt,
        subtitle = leagues.firstOrNull { it.first == league.leagueId }?.second,
        logoMenu = { d -> LeagueMenuItems(leagues, d) },
        hero = {
            if (days.isNotEmpty()) LazyRow(state = dayState, horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 8.dp)) {
                items(days) { d ->
                    val date = runCatching { java.time.LocalDate.parse(d) }.getOrNull()
                    val live = fixtures.any { dayKey(parseTime(it.str("scheduled_at"))) == d && it.str("status") == "in_progress" }
                    DatePill(
                        top = date?.dayOfMonth?.toString() ?: "?",
                        bottom = date?.dayOfWeek?.getDisplayName(java.time.format.TextStyle.SHORT, Locale.getDefault()) ?: "TBC",
                        selected = d == day, mark = live, onClick = { picked = d },
                    )
                }
            }
        },
    ) {
        PullToRefreshBox(isRefreshing = res.loading && res.loaded != null, onRefresh = res.reload, modifier = Modifier.fillMaxSize()) {
            ResBox(res) { _ ->
                if (fixtures.isEmpty()) {
                    Empty(Icons.Filled.CalendarMonth, "No matches yet", "Fixtures appear here once the organiser publishes them.")
                    return@ResBox
                }
                val live = fixtures.filter { it.str("status") == "in_progress" }
                val ofDay = fixtures.filter { dayKey(parseTime(it.str("scheduled_at"))) == day && it.str("status") != "in_progress" }
                LazyColumn(Modifier.fillMaxSize()) {
                    if (live.isNotEmpty()) {
                        item { SectionLabel("Live Now") }
                        items(live, key = { "l" + it.str("match_id") }) { MatchCard(it) { ui.nav.navigate("match/${it.str("match_id")}") } }
                    }
                    item { SectionLabel(day?.let { d -> runCatching { java.time.LocalDate.parse(d).format(DateTimeFormatter.ofPattern("EEEE d MMMM", Locale.getDefault())) }.getOrNull() } ?: "Matches") }
                    if (ofDay.isEmpty()) item {
                        Text("No other matches on this day.", color = extra.muted, modifier = Modifier.padding(horizontal = 20.dp, vertical = 8.dp))
                    }
                    items(ofDay, key = { it.str("match_id") ?: "" }) { MatchCard(it) { ui.nav.navigate("match/${it.str("match_id")}") } }
                    item { Box(Modifier.height(24.dp)) }
                }
            }
        }
    }
}

@Composable
fun MatchCard(f: JsonObject, onClick: () -> Unit) {
    val status = f.str("status")
    val home = f.obj("home")
    val away = f.obj("away")
    val hs = home?.int("score")
    val aws = away?.int("score")
    val t = parseTime(f.str("scheduled_at"))
    val desc = buildString {
        append("${home?.str("name")} versus ${away?.str("name")}. ")
        append(when (status) { "in_progress" -> "Live, $hs to $aws"; "completed" -> "Full time, $hs to $aws"; else -> "Starts ${dayLabel(t)} at ${clock(t)}" })
    }
    WaveCard(
        Modifier.semantics(mergeDescendants = true) { contentDescription = desc }, onClick = onClick,
        badge = {
            when (status) {
                "in_progress" -> BadgePill("Live", dot = true)
                "completed" -> BadgePill("Full time")
                else -> BadgePill(clock(t))
            }
        },
    ) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            TeamBlock(home?.str("name") ?: "To be decided", Modifier.weight(1f))
            Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.width(100.dp)) {
                Text(if (status == "upcoming") "vs" else "${hs ?: 0}-${aws ?: 0}", style = ScoreStyle, fontSize = 30.sp)
                Text(if (status == "upcoming") dayLabel(t) else (if (status == "completed") "Final score" else "In play"),
                    fontSize = 12.sp, color = extra.muted, textAlign = TextAlign.Center)
            }
            TeamBlock(away?.str("name") ?: "To be decided", Modifier.weight(1f))
        }
        f.str("venue")?.let { Text(it, fontSize = 12.sp, color = extra.muted, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth().padding(top = 12.dp)) }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StandingsScreen() {
    val leagues = rememberLeagues()
    val league = LocalLeague.current
    val res = rememberRes(league.leagueId?.let { "/api/v1/leagues/$it/standings" })
    Page("Standings", savedAt = res.loaded?.savedAt, subtitle = leagues.firstOrNull { it.first == league.leagueId }?.second,
        logoMenu = { d -> LeagueMenuItems(leagues, d) }) {
        PullToRefreshBox(isRefreshing = res.loading && res.loaded != null, onRefresh = res.reload, modifier = Modifier.fillMaxSize()) {
            ResBox(res) { l ->
                val table = l.data.arr("table")
                if (table.isEmpty()) {
                    Empty(Icons.Filled.TableRows, "No table yet", "The table appears after the first match is played.")
                    return@ResBox
                }
                val spots = l.data.int("qualification_spots")
                Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
                    SectionLabel(leagues.firstOrNull { it.first == league.leagueId }?.second ?: "Table")
                    StandingsTable(table, spots)
                    Row(Modifier.fillMaxWidth().padding(16.dp), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                        listOf(Qual.CLINCHED, Qual.POSSIBLE, Qual.ELIMINATED).forEach { q ->
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                QualIcon(q, 16); Text(qualLabel(q), fontSize = 12.sp, color = extra.muted)
                            }
                        }
                    }
                    val notes = table.mapNotNull { r -> r.str("resolved_by")?.takeIf { it.isNotBlank() }?.let { "${r.str("name")}: placed by ${com.nascon.app.data.Messages.label(it).lowercase()}" } }
                    if (spots != null) Text("Top $spots qualify. The gold line marks the cut.", fontSize = 12.sp, color = extra.muted, modifier = Modifier.padding(horizontal = 16.dp))
                    if (notes.isNotEmpty()) {
                        SectionLabel("Tie-breaks")
                        notes.forEach { Text(it, fontSize = 13.sp, modifier = Modifier.padding(horizontal = 16.dp, vertical = 2.dp)) }
                    }
                    Box(Modifier.height(24.dp))
                }
            }
        }
    }
}

@Composable
private fun StandingsTable(table: List<JsonObject>, spots: Int?) {
    val headers = listOf("P", "W", "D", "L", "+/-", "Pts")
    BigCard {
        Row(Modifier.fillMaxWidth().height(40.dp).padding(end = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("#", Modifier.width(36.dp), textAlign = TextAlign.Center, style = MaterialTheme.typography.labelSmall, color = extra.muted)
            Text("TEAM", Modifier.weight(1f), style = MaterialTheme.typography.labelSmall, color = extra.muted)
            headers.forEach { Text(it, Modifier.width(27.dp), textAlign = TextAlign.Center, style = MaterialTheme.typography.labelSmall, color = extra.muted) }
            Box(Modifier.width(27.dp))
        }
        CardDivider()
        table.forEachIndexed { i, r ->
            val q = qualOf(r.str("status"))
            val rank = r.int("rank") ?: (i + 1)
            val qualifies = spots != null && rank <= spots
            val desc = "Rank $rank, ${r.str("name")}, ${r.int("points")} points, played ${r.int("played")}, ${qualLabel(q)}"
            Row(
                Modifier.fillMaxWidth().heightIn(min = 48.dp).padding(end = 8.dp).semantics(mergeDescendants = true) { contentDescription = desc },
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Box(Modifier.width(36.dp).height(48.dp), contentAlignment = Alignment.Center) {
                    if (qualifies) Box(Modifier.align(Alignment.CenterStart).width(3.dp).fillMaxHeight().padding(vertical = 12.dp).background(extra.gold))
                    Text("$rank", style = NumStyle, color = extra.muted)
                }
                Row(Modifier.weight(1f), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Crest(r.str("name") ?: "", 20)
                    Text(r.str("name") ?: "", maxLines = 1, overflow = TextOverflow.Ellipsis, fontWeight = FontWeight.Medium)
                }
                listOf(r.int("played"), r.int("won"), r.int("drawn"), r.int("lost")).forEach {
                    Text("${it ?: 0}", Modifier.width(27.dp), textAlign = TextAlign.Center, style = NumStyle)
                }
                val diff = r.int("diff") ?: 0
                Text(if (diff > 0) "+$diff" else "$diff", Modifier.width(27.dp), textAlign = TextAlign.Center, style = NumStyle)
                Text("${r.int("points") ?: 0}", Modifier.width(27.dp), textAlign = TextAlign.Center, style = NumStyle, fontWeight = FontWeight.Bold)
                Box(Modifier.width(27.dp), contentAlignment = Alignment.Center) { QualIcon(q, 18) }
            }
            if (spots != null && rank == spots) Box(Modifier.fillMaxWidth().padding(horizontal = 12.dp).height(2.dp).background(extra.gold)) else if (i < table.lastIndex) CardDivider()
        }
    }
}
