package com.nascon.app.data

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject

data class Loaded(val data: JsonObject, val savedAt: Long, val fromCache: Boolean)

/** Network first, Room cache as fallback. Every successful read refreshes the cache. */
class Repo(private val api: Api, private val db: AppDb, private val session: Session) {
    private fun key(path: String) = (session.current?.user?.email ?: "anon") + "|" + path

    suspend fun cached(path: String): Loaded? =
        db.cache().get(key(path))?.let { Loaded(json.parseToJsonElement(it.body).jsonObject, it.savedAt, true) }

    suspend fun load(path: String): Loaded {
        return try {
            val data = api.get(path)
            val now = System.currentTimeMillis()
            db.cache().put(CacheEntry(key(path), data.toString(), now))
            Loaded(data, now, false)
        } catch (e: ApiError) {
            if (e.isNetwork) cached(path)?.let { return it }
            if (e.isNetwork) throw ApiError(e.code, "You're offline and this hasn't been saved on this phone yet.", 0)
            throw e
        }
    }
}
