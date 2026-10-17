package com.nascon.app.ui

import androidx.compose.foundation.background
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

@Composable
fun LeaguePicker(leagues: List<Pair<String, String>>) {
    val league = LocalLeague.current
    if (leagues.size < 2) return
    Row(
        Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface).horizontalScroll(rememberScrollState())
            .padding(horizontal = 12.dp, vertical = 4.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        leagues.forEach { (id, name) ->
            FilterChip(selected = league.leagueId == id, onClick = { league.leagueId = id }, label = { Text(name) },
                modifier = Modifier.heightIn(min = 40.dp))
        }
    }
}

private val inFmt = DateTimeFormatter.ISO_OFFSET_DATE_TIME
fun parseTime(s: String?): OffsetDateTime? = try { s?.let { OffsetDateTime.parse(it.replace("Z", "+00:00"), inFmt) } } catch (e: Exception) { null }
fun dayLabel(t: OffsetDateTime?) = t?.atZoneSameInstant(ZoneId.systemDefault())?.format(DateTimeFormatter.ofPattern("EEE d MMM", Locale.getDefault())) ?: "Date to be confirmed"
fun clock(t: OffsetDateTime?) = t?.atZoneSameInstant(ZoneId.systemDefault())?.format(DateTimeFormatter.ofPattern("HH:mm")) ?: "TBC"

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FixturesScreen() {
    val ui = LocalUi.current
    val leagues = rememberLeagues()
    val league = LocalLeague.current
    val res = rememberRes(league.leagueId?.let { "/api/v1/leagues/$it/fixtures" })
    Page(leagues.firstOrNull { it.first == league.leagueId }?.second ?: "Fixtures", savedAt = res.loaded?.savedAt) {
        LeaguePicker(leagues)
        if (league.leagueId == null && leagues.isEmpty()) {
            ResBox(res) {}
            if (res.loaded == null && res.error == null) return@Page
        }
        PullToRefreshBox(isRefreshing = res.loading && res.loaded != null, onRefresh = res.reload, modifier = Modifier.fillMaxSize()) {
            ResBox(res) { l ->
                val fixtures = l.data.arr("fixtures").sortedBy { it.str("scheduled_at") ?: "" }
                if (fixtures.isEmpty()) {
                    Empty(Icons.Filled.CalendarMonth, "No matches yet", "Fixtures appear here once the organiser publishes them.")
                    return@ResBox
                }
                val live = fixtures.filter { it.str("status") == "in_progress" }
                val groups = fixtures.filter { it.str("status") != "in_progress" }.groupBy { dayLabel(parseTime(it.str("scheduled_at"))) }
                LazyColumn(Modifier.fillMaxSize()) {
                    if (live.isNotEmpty()) {
                        item { SectionLabel("Live now") }
                        items(live, key = { "l" + it.str("match_id") }) { FixtureRow(it) { ui.nav.navigate("match/${it.str("match_id")}") } }
                    }
                    groups.forEach { (day, list) ->
                        item(key = "h$day") { SectionLabel(day) }
                        items(list, key = { it.str("match_id") ?: "" }) { FixtureRow(it) { ui.nav.navigate("match/${it.str("match_id")}") } }
                    }
                    item { Box(Modifier.height(24.dp)) }
                }
            }
        }
    }
}

@Composable
fun FixtureRow(f: JsonObject, onClick: () -> Unit) {
    val status = f.str("status")
    val home = f.obj("home")
    val away = f.obj("away")
    val done = status == "completed"
    val hs = home?.int("score")
    val aws = away?.int("score")
    val desc = buildString {
        append("${home?.str("name")} versus ${away?.str("name")}. ")
        append(when (status) { "in_progress" -> "Live, $hs to $aws"; "completed" -> "Full time, $hs to $aws"; else -> "Starts ${clock(parseTime(f.str("scheduled_at")))}" })
    }
    Column {
        Row(
            Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface).clickable(onClickLabel = "Open match", onClick = onClick)
                .heightIn(min = 64.dp).semantics(mergeDescendants = true) { contentDescription = desc },
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f).padding(horizontal = 16.dp, vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                TeamLine(home, if (status == "upcoming") null else hs, winner = done && (hs ?: 0) > (aws ?: 0), loser = done && (hs ?: 0) < (aws ?: 0))
                TeamLine(away, if (status == "upcoming") null else aws, winner = done && (aws ?: 0) > (hs ?: 0), loser = done && (aws ?: 0) < (hs ?: 0))
            }
            VerticalDivider(Modifier.height(40.dp), color = extra.line)
            Column(Modifier.width(76.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                when (status) {
                    "in_progress" -> LiveMark()
                    "completed" -> { Text("FT", fontWeight = FontWeight.Medium); Text("Full time", fontSize = 11.sp, color = extra.muted) }
                    else -> { Text(clock(parseTime(f.str("scheduled_at"))), fontWeight = FontWeight.Medium); Text("Upcoming", fontSize = 11.sp, color = extra.muted) }
                }
            }
        }
        Divider()
    }
}

@Composable
private fun TeamLine(team: JsonObject?, score: Int?, winner: Boolean, loser: Boolean) {
    val name = team?.str("name") ?: team?.str("team_id") ?: "To be decided"
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Crest(name, 22)
        Text(name, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis,
            fontWeight = if (winner) FontWeight.Bold else FontWeight.Normal, color = if (loser) extra.muted else MaterialTheme.colorScheme.onSurface)
        Text(score?.toString() ?: "–", style = NumStyle, fontWeight = if (winner) FontWeight.Bold else FontWeight.Medium,
            color = if (loser) extra.muted else MaterialTheme.colorScheme.onSurface)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StandingsScreen() {
    val leagues = rememberLeagues()
    val league = LocalLeague.current
    val res = rememberRes(league.leagueId?.let { "/api/v1/leagues/$it/standings" })
    Page("Standings", savedAt = res.loaded?.savedAt) {
        LeaguePicker(leagues)
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
    Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface)) {
        Row(Modifier.fillMaxWidth().height(32.dp).padding(end = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("#", Modifier.width(36.dp), textAlign = TextAlign.Center, style = MaterialTheme.typography.labelSmall, color = extra.muted)
            Text("TEAM", Modifier.weight(1f), style = MaterialTheme.typography.labelSmall, color = extra.muted)
            headers.forEach { Text(it, Modifier.width(30.dp), textAlign = TextAlign.Center, style = MaterialTheme.typography.labelSmall, color = extra.muted) }
            Box(Modifier.width(30.dp))
        }
        Divider()
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
                    Text("${it ?: 0}", Modifier.width(30.dp), textAlign = TextAlign.Center, style = NumStyle)
                }
                val diff = r.int("diff") ?: 0
                Text(if (diff > 0) "+$diff" else "$diff", Modifier.width(30.dp), textAlign = TextAlign.Center, style = NumStyle)
                Text("${r.int("points") ?: 0}", Modifier.width(30.dp), textAlign = TextAlign.Center, style = NumStyle, fontWeight = FontWeight.Bold)
                Box(Modifier.width(30.dp), contentAlignment = Alignment.Center) { QualIcon(q, 18) }
            }
            if (spots != null && rank == spots) Box(Modifier.fillMaxWidth().height(1.dp).background(extra.gold)) else Divider()
        }
    }
}
