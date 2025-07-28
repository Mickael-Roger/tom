package com.tom.assistant.network

import com.tom.assistant.models.*
import retrofit2.Response
import retrofit2.http.*

interface TomApiService {
    
    @FormUrlEncoded
    @POST("login")
    suspend fun login(
        @Field("username") username: String,
        @Field("password") password: String
    ): Response<Void>
    
    @POST("process")
    suspend fun process(@Body request: ProcessRequest): Response<ProcessResponse>
    
    @GET("tasks")
    suspend fun getTasks(): Response<TasksResponse>
    
    @GET("notifications")
    suspend fun getNotifications(): Response<List<Notification>>
    
    @POST("reset")
    suspend fun reset(): Response<ResetResponse>
}