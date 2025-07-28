package com.tom.assistant.network

import android.content.Context
import okhttp3.CookieJar
import okhttp3.Cookie
import okhttp3.HttpUrl
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.net.CookieManager
import java.net.CookiePolicy
import java.net.CookieStore
import java.util.concurrent.TimeUnit

object ApiClient {
    
    private var persistentCookieStore: PersistentCookieStore? = null
    
    fun initialize(context: Context) {
        persistentCookieStore = PersistentCookieStore(context.applicationContext)
    }
    
    // URL de base de votre serveur Tom via Tailscale
    private const val BASE_URL = "https://server.taila2494.ts.net:8444/"
    
    // Cookie manager pour gérer les sessions avec store persistant
    private val cookieManager by lazy {
        persistentCookieStore?.let { store ->
            CookieManager(store, CookiePolicy.ACCEPT_ALL)
        } ?: CookieManager().apply {
            setCookiePolicy(CookiePolicy.ACCEPT_ALL)
        }
    }
    
    // Custom CookieJar implementation avec persistance
    private val cookieJar = object : CookieJar {
        override fun saveFromResponse(url: HttpUrl, cookies: List<Cookie>) {
            try {
                for (cookie in cookies) {
                    val httpCookie = java.net.HttpCookie(cookie.name, cookie.value).apply {
                        domain = cookie.domain ?: url.host
                        path = cookie.path ?: "/"
                        isHttpOnly = cookie.httpOnly
                        secure = cookie.secure
                        // Force une longue durée de vie pour les sessions
                        if (cookie.expiresAt != Long.MAX_VALUE) {
                            maxAge = (cookie.expiresAt - System.currentTimeMillis()) / 1000
                        } else {
                            // Si pas d'expiration, on donne 30 jours comme le serveur
                            maxAge = 30 * 24 * 3600
                        }
                    }
                    cookieManager.cookieStore.add(url.toUri(), httpCookie)
                }
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }

        override fun loadForRequest(url: HttpUrl): List<Cookie> {
            val cookies = mutableListOf<Cookie>()
            try {
                val storedCookies = cookieManager.cookieStore.get(url.toUri())
                for (httpCookie in storedCookies) {
                    val builder = Cookie.Builder()
                        .name(httpCookie.name)
                        .value(httpCookie.value)
                        .domain(httpCookie.domain ?: url.host)
                        .path(httpCookie.path ?: "/")
                    
                    if (httpCookie.secure) builder.secure()
                    if (httpCookie.isHttpOnly) builder.httpOnly()
                    
                    // Force une expiration longue si pas définie
                    if (httpCookie.maxAge <= 0) {
                        builder.expiresAt(System.currentTimeMillis() + (30L * 24 * 3600 * 1000))
                    }
                    
                    cookies.add(builder.build())
                }
            } catch (e: Exception) {
                e.printStackTrace()
            }
            return cookies
        }
    }
    
    private val httpClient = OkHttpClient.Builder()
        .cookieJar(cookieJar)
        .addInterceptor(HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BODY
        })
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(180, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()
    
    private val retrofit = Retrofit.Builder()
        .baseUrl(BASE_URL)
        .client(httpClient)
        .addConverterFactory(GsonConverterFactory.create())
        .build()
    
    val tomApiService: TomApiService = retrofit.create(TomApiService::class.java)
    
    fun updateBaseUrl(newBaseUrl: String): TomApiService {
        val newRetrofit = Retrofit.Builder()
            .baseUrl(newBaseUrl)
            .client(httpClient)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
        
        return newRetrofit.create(TomApiService::class.java)
    }
}