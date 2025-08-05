package com.tom.assistant

import android.app.Service
import android.content.Intent
import android.os.IBinder
import android.util.Log

class MediaService : Service() {
    
    companion object {
        private const val TAG = "MediaService"
    }
    
    override fun onBind(intent: Intent?): IBinder? {
        return null
    }
    
    override fun onCreate() {
        super.onCreate()
        Log.d(TAG, "MediaService created")
    }
    
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Log.d(TAG, "MediaService started")
        return START_STICKY // Redémarre automatiquement si tué
    }
    
    override fun onDestroy() {
        super.onDestroy()
        Log.d(TAG, "MediaService destroyed")
    }
}