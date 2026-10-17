package com.nascon.app.data

import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.RoomDatabase
import kotlinx.coroutines.flow.Flow

/** Last good server response for a screen, keyed by user and API path. */
@Entity(tableName = "cache")
data class CacheEntry(@PrimaryKey val key: String, val body: String, val savedAt: Long)

/**
 * One offline action. [action] holds the exact /sync action object (spec 5.14).
 * [owner] is the account that created it, so it is sent with that account's token.
 */
@Entity(tableName = "pending_actions")
data class PendingAction(
    @PrimaryKey val actionId: String,
    val owner: String,
    val type: String,
    val title: String,
    val action: String,
    val createdAt: Long,
    val state: String = STATE_PENDING,
    val result: String? = null,
    val resolvedAt: Long? = null,
) {
    companion object {
        const val STATE_PENDING = "pending"
        const val STATE_APPLIED = "applied"
        const val STATE_REJECTED = "rejected"
        const val STATE_DUPLICATE = "duplicate"
    }
}

@Dao
interface CacheDao {
    @Query("SELECT * FROM cache WHERE `key` = :key")
    suspend fun get(key: String): CacheEntry?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun put(e: CacheEntry)
}

@Dao
interface ActionDao {
    @Query("SELECT * FROM pending_actions ORDER BY createdAt")
    fun observeAll(): Flow<List<PendingAction>>

    @Query("SELECT * FROM pending_actions WHERE state = 'pending' ORDER BY createdAt")
    suspend fun pending(): List<PendingAction>

    @Query("SELECT COUNT(*) FROM pending_actions WHERE state = 'pending'")
    fun observePendingCount(): Flow<Int>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun put(a: PendingAction)

    @Query("UPDATE pending_actions SET state = :state, result = :result, resolvedAt = :at WHERE actionId = :id")
    suspend fun resolve(id: String, state: String, result: String, at: Long)

    @Query("DELETE FROM pending_actions WHERE state <> 'pending'")
    suspend fun clearResolved()
}

@Database(entities = [CacheEntry::class, PendingAction::class], version = 1, exportSchema = false)
abstract class AppDb : RoomDatabase() {
    abstract fun cache(): CacheDao
    abstract fun actions(): ActionDao
}
