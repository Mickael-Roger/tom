package com.tom.assistant.models

data class ProcessRequest(
    val request: String,
    val position: Position?,
    val sound_enabled: Boolean,
    val client_type: String = "android"
)

data class Position(
    val latitude: Double,
    val longitude: Double
)