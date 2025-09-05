package com.tom.assistant.models

import com.google.gson.annotations.SerializedName
import java.time.LocalDateTime

/**
 * Health data model representing various health metrics from Health Connect
 */
data class HealthData(
    @SerializedName("timestamp")
    val timestamp: String,
    
    @SerializedName("data_type")
    val dataType: String,
    
    @SerializedName("value")
    val value: Double? = null,
    
    @SerializedName("unit")
    val unit: String? = null,
    
    @SerializedName("start_time")
    val startTime: String? = null,
    
    @SerializedName("end_time")
    val endTime: String? = null,
    
    @SerializedName("additional_data")
    val additionalData: Map<String, String>? = null
)

/**
 * Health data request model for sending health data to server
 */
data class HealthDataRequest(
    @SerializedName("health_data")
    val healthData: List<HealthData>,
    
    @SerializedName("device_info")
    val deviceInfo: DeviceInfo
)

/**
 * Device information for health data context
 */
data class DeviceInfo(
    @SerializedName("device_model")
    val deviceModel: String,
    
    @SerializedName("android_version")
    val androidVersion: String,
    
    @SerializedName("health_connect_version")
    val healthConnectVersion: String? = null
)

/**
 * Health data types enumeration
 */
enum class HealthDataType(val typeName: String, val unit: String) {
    STEPS("steps", "count"),
    HEART_RATE("heart_rate", "bpm"),
    SLEEP("sleep", "minutes"),
    DISTANCE("distance", "meters"),
    CALORIES("calories", "kcal"),
    EXERCISE("exercise", "minutes"),
    BODY_TEMPERATURE("body_temperature", "celsius"),
    BLOOD_PRESSURE_SYSTOLIC("blood_pressure_systolic", "mmHg"),
    BLOOD_PRESSURE_DIASTOLIC("blood_pressure_diastolic", "mmHg"),
    WEIGHT("weight", "kg"),
    HEIGHT("height", "cm")
}