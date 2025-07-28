package com.tom.assistant.models

data class ProcessRequest(
    val request: String,
    val lang: String,
    val position: Position?,
    val tts: Boolean,
    val client_type: String = "android"
)

data class Position(
    val latitude: Double,
    val longitude: Double
)