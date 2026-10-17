package com.nascon.app

import android.app.Application
import android.content.Context
import androidx.compose.runtime.mutableStateListOf
import androidx.room.Room
import com.nascon.app.data.Api
import com.nascon.app.data.AppDb
import com.nascon.app.data.NetworkMonitor
import com.nascon.app.data.Repo
import com.nascon.app.data.SecureStore
import com.nascon.app.data.Session
import com.nascon.app.data.Settings
import com.nascon.app.data.SyncManager
import kotlinx.serialization.json.JsonObject

data class CartLine(val product: JsonObject, val variant: JsonObject, val quantity: Int)

class Graph(context: Context) {
    val settings = Settings(context)
    val secure = SecureStore(context)
    val session = Session(secure).apply { restore() }
    val api = Api(settings) { session.current?.token }
    val db = Room.databaseBuilder(context, AppDb::class.java, "nascon.db").build()
    val repo = Repo(api, db, session) { network.online.value }
    val sync = SyncManager(context, api, db, session, settings)
    val network = NetworkMonitor(context) { sync.schedule() }.also { sync.network = it }
    val cart = mutableStateListOf<CartLine>()
}

class App : Application() {
    lateinit var graph: Graph

    override fun onCreate() {
        super.onCreate()
        graph = Graph(this)
        graph.sync.schedule()
    }
}
