package com.tom.assistant.network

import android.content.Context
import android.content.SharedPreferences
import okhttp3.Cookie
import okhttp3.HttpUrl
import java.net.CookieStore
import java.net.HttpCookie
import java.net.URI

class PersistentCookieStore(private val context: Context) : CookieStore {
    
    private val prefs: SharedPreferences = context.getSharedPreferences("CookiePrefs", Context.MODE_PRIVATE)
    private val cookieMap = mutableMapOf<String, HttpCookie>()
    
    init {
        // Charger les cookies sauvegardés
        loadCookies()
    }
    
    override fun add(uri: URI?, cookie: HttpCookie?) {
        if (uri != null && cookie != null) {
            val key = "${uri.host}_${cookie.name}"
            cookieMap[key] = cookie
            saveCookie(key, cookie)
        }
    }
    
    override fun get(uri: URI?): MutableList<HttpCookie> {
        val result = mutableListOf<HttpCookie>()
        if (uri != null) {
            for ((key, cookie) in cookieMap) {
                if (key.startsWith(uri.host) && !cookie.hasExpired()) {
                    result.add(cookie)
                }
            }
        }
        return result
    }
    
    override fun getCookies(): MutableList<HttpCookie> {
        return cookieMap.values.filter { !it.hasExpired() }.toMutableList()
    }
    
    override fun getURIs(): MutableList<URI> {
        return mutableListOf() // Pas nécessaire pour notre usage
    }
    
    override fun remove(uri: URI?, cookie: HttpCookie?): Boolean {
        if (uri != null && cookie != null) {
            val key = "${uri.host}_${cookie.name}"
            cookieMap.remove(key)
            prefs.edit().remove(key).apply()
            return true
        }
        return false
    }
    
    override fun removeAll(): Boolean {
        cookieMap.clear()
        prefs.edit().clear().apply()
        return true
    }
    
    private fun saveCookie(key: String, cookie: HttpCookie) {
        val cookieString = "${cookie.name}|${cookie.value}|${cookie.domain}|${cookie.path}|${cookie.maxAge}|${cookie.secure}|${cookie.isHttpOnly}"
        prefs.edit().putString(key, cookieString).apply()
    }
    
    private fun loadCookies() {
        for ((key, value) in prefs.all) {
            if (value is String) {
                try {
                    val parts = value.split("|")
                    if (parts.size >= 7) {
                        val cookie = HttpCookie(parts[0], parts[1]).apply {
                            domain = parts[2].takeIf { it.isNotEmpty() }
                            path = parts[3].takeIf { it.isNotEmpty() }
                            maxAge = parts[4].toLongOrNull() ?: -1
                            secure = parts[5].toBoolean()
                            isHttpOnly = parts[6].toBoolean()
                        }
                        if (!cookie.hasExpired()) {
                            cookieMap[key] = cookie
                        }
                    }
                } catch (e: Exception) {
                    // Ignore invalid cookies
                }
            }
        }
    }
}