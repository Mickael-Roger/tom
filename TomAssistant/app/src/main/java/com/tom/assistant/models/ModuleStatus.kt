package com.tom.assistant.models

data class ModuleStatus(
    val name: String,
    val status: String, // "connected" or other status
    val description: String,
    val llm: String,
    val tools_count: Int,
    val enabled: Boolean
)

data class ModuleStatusResponse(
    val modules: List<ModuleStatus>
)