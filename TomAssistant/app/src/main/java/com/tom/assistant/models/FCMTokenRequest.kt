package com.tom.assistant.models

data class FCMTokenRequest(
    val token: String,
    val platform: String
)