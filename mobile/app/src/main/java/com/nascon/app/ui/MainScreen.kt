package com.nascon.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Shield
import androidx.compose.material.icons.filled.ShoppingBag
import androidx.compose.material.icons.filled.TableRows
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.nascon.app.data.SessionState
import com.nascon.app.data.arr
import com.nascon.app.data.str
import com.nascon.app.graph
import kotlinx.coroutines.launch

class Ui(val nav: NavHostController, val session: SessionState, val toast: (String) -> Unit)

val LocalUi = compositionLocalOf<Ui> { error("no ui") }

private data class Tab(val route: String, val label: String, val icon: ImageVector)

private val tabs = listOf(
    Tab("fixtures", "Fixtures", Icons.Filled.CalendarMonth),
    Tab("standings", "Standings", Icons.Filled.TableRows),
    Tab("store", "Store", Icons.Filled.ShoppingBag),
    Tab("club", "Club", Icons.Filled.Shield),
    Tab("profile", "Profile", Icons.Filled.Person),
)

/** The selected league, shared by Fixtures and Standings. */
class LeagueState {
    var leagueId by mutableStateOf<String?>(null)
}

val LocalLeague = compositionLocalOf { LeagueState() }

@Composable
fun MainScreen(session: SessionState) {
    val g = graph()
    val nav = rememberNavController()
    val snack = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()
    val league = remember { LeagueState() }
    val summary by g.sync.lastSummary.collectAsStateWithLifecycle()

    LaunchedEffect(summary) {
        summary?.let { snack.showSnackbar(it); g.sync.clearSummary() }
    }
    LaunchedEffect(session.user.email) {
        try { g.session.updateMe(g.api.get("/api/v1/me")) } catch (e: Exception) { }
    }

    val ui = remember(nav, session) { Ui(nav, session) { msg -> scope.launch { snack.showSnackbar(msg) } } }
    val entry by nav.currentBackStackEntryAsState()
    val route = entry?.destination?.route

    CompositionLocalProvider(LocalUi provides ui, LocalLeague provides league) {
        Scaffold(
            snackbarHost = { SnackbarHost(snack) },
            bottomBar = {
                NavigationBar(containerColor = MaterialTheme.colorScheme.surface) {
                    tabs.forEach { t ->
                        val selected = route == t.route || (route != null && tabOf(route) == t.route)
                        NavigationBarItem(
                            selected = selected,
                            onClick = {
                                nav.navigate(t.route) {
                                    popUpTo(nav.graph.findStartDestination().id) { saveState = true }
                                    launchSingleTop = true
                                    restoreState = true
                                }
                            },
                            icon = { Icon(t.icon, contentDescription = null) },
                            label = { Text(t.label) },
                            colors = NavigationBarItemDefaults.colors(
                                selectedIconColor = extra.link, selectedTextColor = extra.link,
                                indicatorColor = extra.tint,
                            ),
                        )
                    }
                }
            },
        ) { pad ->
            Box(Modifier.padding(pad).fillMaxSize().background(MaterialTheme.colorScheme.background)) {
                NavHost(nav, startDestination = "fixtures") {
                    composable("fixtures") { FixturesScreen() }
                    composable("standings") { StandingsScreen() }
                    composable("store") { StoreScreen() }
                    composable("club") { ClubTab() }
                    composable("profile") { ProfileScreen() }
                    composable("match/{id}") { MatchScreen(it.arguments?.getString("id") ?: "") }
                    composable("clubs/{id}") { ClubScreen(it.arguments?.getString("id") ?: "", back = true) }
                    composable("product/{id}") { ProductScreen(it.arguments?.getString("id") ?: "") }
                    composable("cart") { CartScreen() }
                    composable("receipt/{id}") { ReceiptScreen(it.arguments?.getString("id") ?: "") }
                    composable("orders") { OrdersScreen() }
                    composable("queue") { QueueScreen() }
                }
            }
        }
    }
}

private fun tabOf(route: String) = when {
    route.startsWith("match") -> "fixtures"
    route.startsWith("clubs") -> "club"
    route.startsWith("product") || route == "cart" || route.startsWith("receipt") || route == "orders" -> "store"
    route == "queue" -> "profile"
    else -> null
}

/** Screen frame: top bar, the always-visible connection bar, then content. */
@Composable
fun Page(
    title: String,
    back: Boolean = false,
    savedAt: Long? = null,
    actions: @Composable () -> Unit = {},
    content: @Composable ColumnScope.() -> Unit,
) {
    val g = graph()
    val ui = LocalUi.current
    val online by g.network.online.collectAsStateWithLifecycle()
    val syncing by g.sync.syncing.collectAsStateWithLifecycle()
    val pending by g.db.actions().observePendingCount().collectAsStateWithLifecycle(0)
    Column(Modifier.fillMaxSize()) {
        Bar(title, onBack = if (back) ({ ui.nav.popBackStack() }) else null, logo = ui.session.branding.logoText, actions = actions)
        NetBar(online, syncing, pending, if (online) null else savedAt) { ui.nav.navigate("queue") { launchSingleTop = true } }
        content()
    }
}

/** League picker data shared by Fixtures and Standings. */
@Composable
fun rememberLeagues(): List<Pair<String, String>> {
    val res = rememberRes("/api/v1/leagues")
    val league = LocalLeague.current
    val ui = LocalUi.current
    val list = res.loaded?.data?.arr("leagues")?.mapNotNull { l -> l.str("league_id")?.let { it to (l.str("name") ?: it) } } ?: emptyList()
    LaunchedEffect(list) {
        if (league.leagueId == null && list.isNotEmpty()) {
            league.leagueId = list.firstOrNull { it.first == ui.session.user.leagueId }?.first ?: list.first().first
        }
    }
    return list
}

@Composable
fun rememberStr(v: String) = rememberSaveable { mutableStateOf(v) }
