package com.nascon.app.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.util.concurrent.TimeUnit

class ApiError(val code: String, override val message: String, val status: Int) : Exception(message) {
    val isNetwork get() = code == NETWORK

    companion object {
        const val NETWORK = "NETWORK"
    }
}

val json = Json { ignoreUnknownKeys = true; explicitNulls = false }

class Api(private val settings: Settings, private val token: () -> String?) {
    val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(6, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .pingInterval(20, TimeUnit.SECONDS)
        .build()

    fun base() = settings.serverUrl.trimEnd('/')

    suspend fun get(path: String, auth: String? = null): JsonObject = call(Request.Builder().url(base() + path).get(), auth)

    suspend fun post(path: String, body: JsonElement, auth: String? = null): JsonObject =
        call(Request.Builder().url(base() + path).post(body.toString().toRequestBody(JSON_TYPE)), auth)

    suspend fun delete(path: String): JsonObject = call(Request.Builder().url(base() + path).delete(), null)

    suspend fun bytes(path: String): ByteArray = withContext(Dispatchers.IO) {
        val b = Request.Builder().url(base() + path).get()
        token()?.let { b.header("Authorization", "Bearer $it") }
        try {
            client.newCall(b.build()).execute().use { r ->
                if (!r.isSuccessful) throw parseError(r.code, r.body?.string().orEmpty())
                r.body?.bytes() ?: ByteArray(0)
            }
        } catch (e: IOException) {
            throw ApiError(ApiError.NETWORK, Messages.NETWORK, 0)
        }
    }

    private suspend fun call(b: Request.Builder, auth: String?): JsonObject = withContext(Dispatchers.IO) {
        (auth ?: token())?.let { b.header("Authorization", "Bearer $it") }
        try {
            client.newCall(b.build()).execute().use { r ->
                val text = r.body?.string().orEmpty()
                if (!r.isSuccessful) throw parseError(r.code, text)
                if (text.isBlank()) JsonObject(emptyMap()) else json.parseToJsonElement(text).jsonObject
            }
        } catch (e: IOException) {
            throw ApiError(ApiError.NETWORK, Messages.NETWORK, 0)
        } catch (e: IllegalArgumentException) {
            throw ApiError("BAD_RESPONSE", "The server sent something unexpected. Check the server address.", 0)
        }
    }

    private fun parseError(status: Int, text: String): ApiError {
        val code = try {
            json.parseToJsonElement(text).jsonObject.obj("error")?.str("code")
        } catch (e: Exception) {
            null
        } ?: when (status) {
            401 -> "UNAUTHORIZED"
            403 -> "FORBIDDEN"
            404 -> "NOT_FOUND"
            429 -> "RATE_LIMITED"
            else -> "SERVER"
        }
        return ApiError(code, Messages.forCode(code), status)
    }

    companion object {
        private val JSON_TYPE = "application/json".toMediaType()
    }
}
