package com.tom.assistant.services

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import com.tom.assistant.MainActivity
import com.tom.assistant.R
import com.tom.assistant.models.FCMTokenRequest
import com.tom.assistant.network.ApiClient
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class TomFirebaseMessagingService : FirebaseMessagingService() {

    companion object {
        private const val TAG = "TomFCMService"
    }

    override fun onNewToken(token: String) {
        super.onNewToken(token)
        Log.d(TAG, "Refreshed token: $token")
        sendTokenToServer(token)
    }

    override fun onMessageReceived(remoteMessage: RemoteMessage) {
        super.onMessageReceived(remoteMessage)
        Log.d(TAG, "From: ${remoteMessage.from}")

        remoteMessage.data.isNotEmpty().let {
            Log.d(TAG, "Message data payload: " + remoteMessage.data)
            val title = remoteMessage.data["title"] ?: "Nouvelle notification"
            val body = remoteMessage.data["body"] ?: "Vous avez un nouveau message."
            sendNotification(title, body)
        }
    }

    private fun sendNotification(title: String, messageBody: String) {
        val intent = Intent(this, MainActivity::class.java)
        intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP)
        val pendingIntent = PendingIntent.getActivity(this, 0, intent,
            PendingIntent.FLAG_ONE_SHOT or PendingIntent.FLAG_IMMUTABLE)

        val channelId = "fcm_default_channel"
        val notificationBuilder = NotificationCompat.Builder(this, channelId)
            .setSmallIcon(R.drawable.ic_tasks_new) // Utilisation d'une icône existante
            .setContentTitle(title)
            .setContentText(messageBody)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)

        val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(channelId,
                "Notifications",
                NotificationManager.IMPORTANCE_DEFAULT)
            notificationManager.createNotificationChannel(channel)
        }

        notificationManager.notify(0, notificationBuilder.build())
    }

    private fun sendTokenToServer(token: String?) {
        if (token.isNullOrBlank()) {
            return
        }
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val request = FCMTokenRequest(token = token, platform = "android_native")
                ApiClient.tomApiService.sendFCMToken(request)
                Log.d(TAG, "FCM token sent to server successfully.")
            } catch (e: Exception) {
                Log.e(TAG, "Error sending FCM token to server", e)
            }
        }
    }
}
