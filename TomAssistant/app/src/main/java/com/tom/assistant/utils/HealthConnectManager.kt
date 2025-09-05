package com.tom.assistant.utils

import android.content.Context
import android.content.SharedPreferences
import android.os.Build
import android.util.Log
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.*
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import com.tom.assistant.models.*
import com.tom.assistant.network.ApiClient
import kotlinx.coroutines.*
import java.time.Instant
import java.time.LocalDateTime
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter

class HealthConnectManager(private val context: Context) {
    
    private val healthConnectClient = HealthConnectClient.getOrCreate(context)
    private val sharedPrefs: SharedPreferences = context.getSharedPreferences("health_data", Context.MODE_PRIVATE)
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    
    companion object {
        private const val TAG = "HealthConnectManager"
        private const val LAST_SYNC_KEY = "last_health_sync"
    }
    
    // Health Connect permissions required
    private val permissions = setOf(
        HealthPermission.getReadPermission(StepsRecord::class),
        HealthPermission.getReadPermission(HeartRateRecord::class),
        HealthPermission.getReadPermission(SleepSessionRecord::class),
        HealthPermission.getReadPermission(DistanceRecord::class),
        HealthPermission.getReadPermission(TotalCaloriesBurnedRecord::class),
        HealthPermission.getReadPermission(ExerciseSessionRecord::class),
        HealthPermission.getReadPermission(BodyTemperatureRecord::class),
        HealthPermission.getReadPermission(BloodPressureRecord::class),
        HealthPermission.getReadPermission(WeightRecord::class),
        HealthPermission.getReadPermission(HeightRecord::class)
    )
    
    /**
     * Check if Health Connect is available on this device
     * Simply returns true and lets the actual Health Connect calls handle availability
     */
    fun isHealthConnectAvailable(): Boolean {
        return true
    }
    
    /**
     * Check if all required permissions are granted
     */
    suspend fun hasAllPermissions(): Boolean {
        return try {
            val grantedPermissions = healthConnectClient.permissionController.getGrantedPermissions()
            permissions.all { it in grantedPermissions }
        } catch (e: Exception) {
            Log.e(TAG, "Error checking permissions", e)
            false
        }
    }
    
    /**
     * Request Health Connect permissions
     */
    suspend fun requestPermissions(): Boolean {
        return try {
            val permissionController = healthConnectClient.permissionController
            // Note: This would typically be called from an Activity context
            // The actual permission request needs to be handled in the Activity
            hasAllPermissions()
        } catch (e: Exception) {
            Log.e(TAG, "Error requesting permissions", e)
            false
        }
    }
    
    /**
     * Start monitoring health data changes and sync periodically
     */
    fun startHealthDataMonitoring() {
        scope.launch {
            while (true) {
                try {
                    if (hasAllPermissions()) {
                        syncHealthData()
                    } else {
                        Log.w(TAG, "Health Connect permissions not granted")
                    }
                    
                    // Wait 30 minutes before next sync
                    delay(30 * 60 * 1000L)
                } catch (e: Exception) {
                    Log.e(TAG, "Error in health data monitoring", e)
                    // Wait 5 minutes on error before retrying
                    delay(5 * 60 * 1000L)
                }
            }
        }
    }
    
    /**
     * Stop health data monitoring
     */
    fun stopHealthDataMonitoring() {
        scope.cancel()
    }
    
    /**
     * Sync health data since last sync
     */
    private suspend fun syncHealthData() {
        try {
            val lastSync = getLastSyncTime()
            val now = Instant.now()
            
            Log.d(TAG, "Syncing health data since: $lastSync")
            
            val healthDataList = mutableListOf<HealthData>()
            
            // Collect different types of health data
            healthDataList.addAll(getStepsData(lastSync, now))
            healthDataList.addAll(getHeartRateData(lastSync, now))
            healthDataList.addAll(getSleepData(lastSync, now))
            healthDataList.addAll(getDistanceData(lastSync, now))
            healthDataList.addAll(getCaloriesData(lastSync, now))
            healthDataList.addAll(getExerciseData(lastSync, now))
            healthDataList.addAll(getBodyTemperatureData(lastSync, now))
            healthDataList.addAll(getBloodPressureData(lastSync, now))
            healthDataList.addAll(getWeightData(lastSync, now))
            healthDataList.addAll(getHeightData(lastSync, now))
            
            if (healthDataList.isNotEmpty()) {
                sendHealthDataToServer(healthDataList)
                updateLastSyncTime(now)
                Log.d(TAG, "Synced ${healthDataList.size} health data records")
            } else {
                Log.d(TAG, "No new health data to sync")
            }
            
        } catch (e: Exception) {
            Log.e(TAG, "Error syncing health data", e)
        }
    }
    
    /**
     * Get steps data
     */
    private suspend fun getStepsData(startTime: Instant, endTime: Instant): List<HealthData> {
        return try {
            val response = healthConnectClient.readRecords(
                ReadRecordsRequest(
                    recordType = StepsRecord::class,
                    timeRangeFilter = TimeRangeFilter.between(startTime, endTime)
                )
            )
            
            response.records.map { record ->
                HealthData(
                    timestamp = record.startTime.toString(),
                    dataType = HealthDataType.STEPS.typeName,
                    value = record.count.toDouble(),
                    unit = HealthDataType.STEPS.unit,
                    startTime = record.startTime.toString(),
                    endTime = record.endTime.toString()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error reading steps data", e)
            emptyList()
        }
    }
    
    /**
     * Get heart rate data
     */
    private suspend fun getHeartRateData(startTime: Instant, endTime: Instant): List<HealthData> {
        return try {
            val response = healthConnectClient.readRecords(
                ReadRecordsRequest(
                    recordType = HeartRateRecord::class,
                    timeRangeFilter = TimeRangeFilter.between(startTime, endTime)
                )
            )
            
            response.records.flatMap { record ->
                record.samples.map { sample ->
                    HealthData(
                        timestamp = sample.time.toString(),
                        dataType = HealthDataType.HEART_RATE.typeName,
                        value = sample.beatsPerMinute.toDouble(),
                        unit = HealthDataType.HEART_RATE.unit
                    )
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error reading heart rate data", e)
            emptyList()
        }
    }
    
    /**
     * Get sleep data
     */
    private suspend fun getSleepData(startTime: Instant, endTime: Instant): List<HealthData> {
        return try {
            val response = healthConnectClient.readRecords(
                ReadRecordsRequest(
                    recordType = SleepSessionRecord::class,
                    timeRangeFilter = TimeRangeFilter.between(startTime, endTime)
                )
            )
            
            response.records.map { record ->
                val durationMinutes = java.time.Duration.between(record.startTime, record.endTime).toMinutes()
                
                HealthData(
                    timestamp = record.startTime.toString(),
                    dataType = HealthDataType.SLEEP.typeName,
                    value = durationMinutes.toDouble(),
                    unit = HealthDataType.SLEEP.unit,
                    startTime = record.startTime.toString(),
                    endTime = record.endTime.toString(),
                    additionalData = mapOf(
                        "title" to (record.title ?: ""),
                        "notes" to (record.notes ?: "")
                    )
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error reading sleep data", e)
            emptyList()
        }
    }
    
    /**
     * Get distance data
     */
    private suspend fun getDistanceData(startTime: Instant, endTime: Instant): List<HealthData> {
        return try {
            val response = healthConnectClient.readRecords(
                ReadRecordsRequest(
                    recordType = DistanceRecord::class,
                    timeRangeFilter = TimeRangeFilter.between(startTime, endTime)
                )
            )
            
            response.records.map { record ->
                HealthData(
                    timestamp = record.startTime.toString(),
                    dataType = HealthDataType.DISTANCE.typeName,
                    value = record.distance.inMeters,
                    unit = HealthDataType.DISTANCE.unit,
                    startTime = record.startTime.toString(),
                    endTime = record.endTime.toString()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error reading distance data", e)
            emptyList()
        }
    }
    
    /**
     * Get calories data
     */
    private suspend fun getCaloriesData(startTime: Instant, endTime: Instant): List<HealthData> {
        return try {
            val response = healthConnectClient.readRecords(
                ReadRecordsRequest(
                    recordType = TotalCaloriesBurnedRecord::class,
                    timeRangeFilter = TimeRangeFilter.between(startTime, endTime)
                )
            )
            
            response.records.map { record ->
                HealthData(
                    timestamp = record.startTime.toString(),
                    dataType = HealthDataType.CALORIES.typeName,
                    value = record.energy.inKilocalories,
                    unit = HealthDataType.CALORIES.unit,
                    startTime = record.startTime.toString(),
                    endTime = record.endTime.toString()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error reading calories data", e)
            emptyList()
        }
    }
    
    /**
     * Get exercise data
     */
    private suspend fun getExerciseData(startTime: Instant, endTime: Instant): List<HealthData> {
        return try {
            val response = healthConnectClient.readRecords(
                ReadRecordsRequest(
                    recordType = ExerciseSessionRecord::class,
                    timeRangeFilter = TimeRangeFilter.between(startTime, endTime)
                )
            )
            
            response.records.map { record ->
                val durationMinutes = java.time.Duration.between(record.startTime, record.endTime).toMinutes()
                
                HealthData(
                    timestamp = record.startTime.toString(),
                    dataType = HealthDataType.EXERCISE.typeName,
                    value = durationMinutes.toDouble(),
                    unit = HealthDataType.EXERCISE.unit,
                    startTime = record.startTime.toString(),
                    endTime = record.endTime.toString(),
                    additionalData = mapOf(
                        "exercise_type" to record.exerciseType.toString(),
                        "title" to (record.title ?: ""),
                        "notes" to (record.notes ?: "")
                    )
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error reading exercise data", e)
            emptyList()
        }
    }
    
    /**
     * Get body temperature data
     */
    private suspend fun getBodyTemperatureData(startTime: Instant, endTime: Instant): List<HealthData> {
        return try {
            val response = healthConnectClient.readRecords(
                ReadRecordsRequest(
                    recordType = BodyTemperatureRecord::class,
                    timeRangeFilter = TimeRangeFilter.between(startTime, endTime)
                )
            )
            
            response.records.map { record ->
                HealthData(
                    timestamp = record.time.toString(),
                    dataType = HealthDataType.BODY_TEMPERATURE.typeName,
                    value = record.temperature.inCelsius,
                    unit = HealthDataType.BODY_TEMPERATURE.unit,
                    additionalData = mapOf(
                        "measurement_location" to record.measurementLocation.toString()
                    )
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error reading body temperature data", e)
            emptyList()
        }
    }
    
    /**
     * Get blood pressure data
     */
    private suspend fun getBloodPressureData(startTime: Instant, endTime: Instant): List<HealthData> {
        return try {
            val response = healthConnectClient.readRecords(
                ReadRecordsRequest(
                    recordType = BloodPressureRecord::class,
                    timeRangeFilter = TimeRangeFilter.between(startTime, endTime)
                )
            )
            
            response.records.flatMap { record ->
                listOf(
                    HealthData(
                        timestamp = record.time.toString(),
                        dataType = HealthDataType.BLOOD_PRESSURE_SYSTOLIC.typeName,
                        value = record.systolic.inMillimetersOfMercury,
                        unit = HealthDataType.BLOOD_PRESSURE_SYSTOLIC.unit,
                        additionalData = mapOf(
                            "measurement_location" to record.measurementLocation.toString(),
                            "body_position" to record.bodyPosition.toString()
                        )
                    ),
                    HealthData(
                        timestamp = record.time.toString(),
                        dataType = HealthDataType.BLOOD_PRESSURE_DIASTOLIC.typeName,
                        value = record.diastolic.inMillimetersOfMercury,
                        unit = HealthDataType.BLOOD_PRESSURE_DIASTOLIC.unit,
                        additionalData = mapOf(
                            "measurement_location" to record.measurementLocation.toString(),
                            "body_position" to record.bodyPosition.toString()
                        )
                    )
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error reading blood pressure data", e)
            emptyList()
        }
    }
    
    /**
     * Get weight data
     */
    private suspend fun getWeightData(startTime: Instant, endTime: Instant): List<HealthData> {
        return try {
            val response = healthConnectClient.readRecords(
                ReadRecordsRequest(
                    recordType = WeightRecord::class,
                    timeRangeFilter = TimeRangeFilter.between(startTime, endTime)
                )
            )
            
            response.records.map { record ->
                HealthData(
                    timestamp = record.time.toString(),
                    dataType = HealthDataType.WEIGHT.typeName,
                    value = record.weight.inKilograms,
                    unit = HealthDataType.WEIGHT.unit
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error reading weight data", e)
            emptyList()
        }
    }
    
    /**
     * Get height data
     */
    private suspend fun getHeightData(startTime: Instant, endTime: Instant): List<HealthData> {
        return try {
            val response = healthConnectClient.readRecords(
                ReadRecordsRequest(
                    recordType = HeightRecord::class,
                    timeRangeFilter = TimeRangeFilter.between(startTime, endTime)
                )
            )
            
            response.records.map { record ->
                HealthData(
                    timestamp = record.time.toString(),
                    dataType = HealthDataType.HEIGHT.typeName,
                    value = record.height.inMeters * 100, // Convert to cm
                    unit = HealthDataType.HEIGHT.unit
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error reading height data", e)
            emptyList()
        }
    }
    
    /**
     * Send health data to server
     */
    private suspend fun sendHealthDataToServer(healthData: List<HealthData>) {
        try {
            val deviceInfo = DeviceInfo(
                deviceModel = Build.MODEL,
                androidVersion = Build.VERSION.RELEASE,
                healthConnectVersion = getHealthConnectVersion()
            )
            
            val request = HealthDataRequest(
                healthData = healthData,
                deviceInfo = deviceInfo
            )
            
            val apiService = ApiClient.tomApiService
            val response = apiService.sendHealthData(request)
            
            if (response.isSuccessful) {
                Log.d(TAG, "Health data sent successfully")
            } else {
                Log.e(TAG, "Failed to send health data: ${response.code()} ${response.message()}")
            }
            
        } catch (e: Exception) {
            Log.e(TAG, "Error sending health data to server", e)
        }
    }
    
    /**
     * Get Health Connect version
     */
    private fun getHealthConnectVersion(): String? {
        return try {
            val packageManager = context.packageManager
            val packageInfo = packageManager.getPackageInfo("com.google.android.apps.healthdata", 0)
            packageInfo.versionName
        } catch (e: Exception) {
            null
        }
    }
    
    /**
     * Get last sync time
     */
    private fun getLastSyncTime(): Instant {
        val lastSyncMillis = sharedPrefs.getLong(LAST_SYNC_KEY, 0L)
        return if (lastSyncMillis == 0L) {
            // If never synced, get data from last 7 days
            Instant.now().minusSeconds(7 * 24 * 60 * 60)
        } else {
            Instant.ofEpochMilli(lastSyncMillis)
        }
    }
    
    /**
     * Update last sync time
     */
    private fun updateLastSyncTime(time: Instant) {
        sharedPrefs.edit()
            .putLong(LAST_SYNC_KEY, time.toEpochMilli())
            .apply()
    }
    
    /**
     * Get the required permissions for the permission request contract
     */
    fun getPermissions(): Set<String> = permissions
}