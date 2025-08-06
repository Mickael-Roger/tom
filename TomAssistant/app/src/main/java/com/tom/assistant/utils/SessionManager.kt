package com.tom.assistant.utils

import android.content.Context
import android.content.SharedPreferences

class SessionManager(context: Context) {
    
    private val sharedPreferences: SharedPreferences = context.getSharedPreferences(
        PREF_NAME, Context.MODE_PRIVATE
    )
    
    companion object {
        private const val PREF_NAME = "TomSession"
        private const val KEY_IS_LOGGED_IN = "isLoggedIn"
        private const val KEY_USERNAME = "username"
        private const val KEY_SERVER_URL = "serverUrl"
        private const val KEY_SOUND_ENABLED = "soundEnabled"
        private const val KEY_AUTO_SUBMIT = "autoSubmit"
        private const val DEFAULT_SERVER_URL = "https://server.taila2494.ts.net:8444/"
    }
    
    fun saveLoginSession(username: String) {
        val editor = sharedPreferences.edit()
        editor.putBoolean(KEY_IS_LOGGED_IN, true)
        editor.putString(KEY_USERNAME, username)
        editor.apply()
    }
    
    fun isLoggedIn(): Boolean {
        return sharedPreferences.getBoolean(KEY_IS_LOGGED_IN, false)
    }
    
    fun getUsername(): String? {
        return sharedPreferences.getString(KEY_USERNAME, null)
    }
    
    fun logout() {
        val editor = sharedPreferences.edit()
        editor.clear()
        editor.apply()
    }
    
    fun getServerUrl(): String {
        return sharedPreferences.getString(KEY_SERVER_URL, DEFAULT_SERVER_URL) ?: DEFAULT_SERVER_URL
    }
    
    fun saveServerUrl(url: String) {
        val editor = sharedPreferences.edit()
        editor.putString(KEY_SERVER_URL, url)
        editor.apply()
    }
    
    fun isSoundEnabled(): Boolean {
        return sharedPreferences.getBoolean(KEY_SOUND_ENABLED, true)
    }
    
    fun saveSoundEnabled(enabled: Boolean) {
        val editor = sharedPreferences.edit()
        editor.putBoolean(KEY_SOUND_ENABLED, enabled)
        editor.apply()
    }
    
    fun isAutoSubmitEnabled(): Boolean {
        return sharedPreferences.getBoolean(KEY_AUTO_SUBMIT, false)
    }
    
    fun saveAutoSubmitEnabled(enabled: Boolean) {
        val editor = sharedPreferences.edit()
        editor.putBoolean(KEY_AUTO_SUBMIT, enabled)
        editor.apply()
    }
}