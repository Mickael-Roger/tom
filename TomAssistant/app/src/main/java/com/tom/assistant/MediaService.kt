package com.tom.assistant

import android.app.Service
import android.content.Intent
import android.os.IBinder
import android.widget.Toast

class MediaService : Service() {
    
    override fun onBind(intent: Intent?): IBinder? {
        return null
    }
    
    override fun onCreate() {
        super.onCreate()
        Toast.makeText(this, "MediaService créé", Toast.LENGTH_SHORT).show()
    }
    
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Toast.makeText(this, "MediaService démarré", Toast.LENGTH_SHORT).show()
        return START_STICKY // Redémarre automatiquement si tué
    }
    
    override fun onDestroy() {
        super.onDestroy()
        Toast.makeText(this, "MediaService détruit", Toast.LENGTH_SHORT).show()
    }
}