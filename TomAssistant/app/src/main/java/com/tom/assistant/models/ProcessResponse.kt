package com.tom.assistant.models

data class ProcessResponse(
    val response: String
)

data class TasksResponse(
    val background_tasks: List<BackgroundTask>,
    val id: Int
)

data class BackgroundTask(
    val module: String,
    val status: String
)

data class NotificationsResponse(
    val notifications: List<Notification>
)

data class Notification(
    val datetime: String,
    val message: String
)

data class ResetResponse(
    val success: Boolean
)