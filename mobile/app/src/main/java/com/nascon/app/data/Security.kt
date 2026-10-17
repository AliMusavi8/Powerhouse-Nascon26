package com.nascon.app.data

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import java.security.MessageDigest
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Small key-value store whose values are encrypted with an AES-GCM key held in the Android Keystore. */
class SecureStore(context: Context) {
    private val prefs = context.getSharedPreferences("secure_store", Context.MODE_PRIVATE)

    private fun key(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getEntry(ALIAS, null) as? KeyStore.SecretKeyEntry)?.let { return it.secretKey }
        val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        gen.init(
            KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build()
        )
        return gen.generateKey()
    }

    fun put(name: String, value: String) {
        val cipher = Cipher.getInstance(TRANSFORM)
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val ct = cipher.doFinal(value.toByteArray(Charsets.UTF_8))
        val packed = b64(cipher.iv) + ":" + b64(ct)
        prefs.edit().putString(name, packed).apply()
    }

    fun get(name: String): String? {
        val packed = prefs.getString(name, null) ?: return null
        return try {
            val (iv, ct) = packed.split(":").map { Base64.decode(it, Base64.NO_WRAP) }
            val cipher = Cipher.getInstance(TRANSFORM)
            cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, iv))
            String(cipher.doFinal(ct), Charsets.UTF_8)
        } catch (e: Exception) {
            null
        }
    }

    fun remove(name: String) = prefs.edit().remove(name).apply()

    private fun b64(b: ByteArray) = Base64.encodeToString(b, Base64.NO_WRAP)

    companion object {
        private const val ALIAS = "nascon_token_key"
        private const val TRANSFORM = "AES/GCM/NoPadding"

        fun hash(email: String, password: String): String {
            val d = MessageDigest.getInstance("SHA-256").digest("${email.lowercase()}|$password".toByteArray())
            return d.joinToString("") { "%02x".format(it) }
        }
    }
}

class Settings(context: Context) {
    private val prefs = context.getSharedPreferences("settings", Context.MODE_PRIVATE)

    var serverUrl: String
        get() = prefs.getString("server_url", DEFAULT_URL) ?: DEFAULT_URL
        set(v) = prefs.edit().putString("server_url", v.trim().trimEnd('/')).apply()

    var deviceId: String
        get() = prefs.getString("device_id", null) ?: ("dev-" + java.util.UUID.randomUUID().toString().take(12)).also { deviceId = it }
        set(v) = prefs.edit().putString("device_id", v).apply()

    var lastEmail: String
        get() = prefs.getString("last_email", "") ?: ""
        set(v) = prefs.edit().putString("last_email", v).apply()

    companion object {
        const val DEFAULT_URL = "http://10.0.2.2:8080"
    }
}
