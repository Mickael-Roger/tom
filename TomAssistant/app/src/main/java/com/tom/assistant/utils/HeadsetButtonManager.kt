package com.tom.assistant.utils

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.media.AudioManager
import android.os.Handler
import android.os.Looper
import androidx.media.session.MediaButtonReceiver
import android.support.v4.media.session.MediaSessionCompat
import android.support.v4.media.session.PlaybackStateCompat
import android.util.Log
import android.view.KeyEvent

class HeadsetButtonManager(
    private val context: Context,
    private val onToggleRecording: () -> Unit
) {
    
    private var mediaSession: MediaSessionCompat? = null
    private var audioManager: AudioManager? = null
    private var headsetReceiver: BroadcastReceiver? = null
    private var isHeadsetConnected = false
    private val handler = Handler(Looper.getMainLooper())
    
    // Variables pour détecter double-clic
    private var lastClickTime = 0L
    private val DOUBLE_CLICK_TIME_DELTA = 300L // 300ms pour double-clic
    
    fun initialize() {
        audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        setupMediaSession()
        setupHeadsetReceiver()
        checkHeadsetConnection()
    }
    
    private fun setupMediaSession() {
        mediaSession = MediaSessionCompat(context, "TomAssistant").apply {
            // Configuration des flags pour recevoir les événements de boutons
            setFlags(
                MediaSessionCompat.FLAG_HANDLES_MEDIA_BUTTONS or
                MediaSessionCompat.FLAG_HANDLES_TRANSPORT_CONTROLS
            )
            
            // État de lecture initial
            setPlaybackState(
                PlaybackStateCompat.Builder()
                    .setActions(
                        PlaybackStateCompat.ACTION_PLAY or
                        PlaybackStateCompat.ACTION_PAUSE or
                        PlaybackStateCompat.ACTION_PLAY_PAUSE
                    )
                    .setState(PlaybackStateCompat.STATE_STOPPED, 0, 1.0f)
                    .build()
            )
            
            // Callback pour les boutons média
            setCallback(object : MediaSessionCompat.Callback() {
                override fun onMediaButtonEvent(mediaButtonEvent: Intent?): Boolean {
                    val keyEvent = mediaButtonEvent?.getParcelableExtra<KeyEvent>(Intent.EXTRA_KEY_EVENT)
                    if (keyEvent?.action == KeyEvent.ACTION_DOWN) {
                        when (keyEvent.keyCode) {
                            KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE,
                            KeyEvent.KEYCODE_HEADSETHOOK,
                            KeyEvent.KEYCODE_MEDIA_PLAY,
                            KeyEvent.KEYCODE_MEDIA_PAUSE -> {
                                handleMediaButtonClick()
                                return true
                            }
                        }
                    }
                    return super.onMediaButtonEvent(mediaButtonEvent)
                }
                
                override fun onPlay() {
                    handleMediaButtonClick()
                }
                
                override fun onPause() {
                    handleMediaButtonClick()
                }
                
                override fun onPlayFromSearch(query: String?, extras: android.os.Bundle?) {
                    handleMediaButtonClick()
                }
            })
            
            isActive = true
        }
    }
    
    private fun handleMediaButtonClick() {
        val currentTime = System.currentTimeMillis()
        
        if (currentTime - lastClickTime < DOUBLE_CLICK_TIME_DELTA) {
            // Double-clic détecté - ignorer car on ne veut qu'un simple clic
            return
        }
        
        lastClickTime = currentTime
        
        // Attendre un peu pour s'assurer qu'il n'y a pas de double-clic
        handler.postDelayed({
            if (System.currentTimeMillis() - lastClickTime >= DOUBLE_CLICK_TIME_DELTA - 50) {
                Log.d("HeadsetButton", "Media button clicked - toggling recording")
                onToggleRecording()
            }
        }, DOUBLE_CLICK_TIME_DELTA + 50)
    }
    
    private fun setupHeadsetReceiver() {
        headsetReceiver = object : BroadcastReceiver() {
            override fun onReceive(context: Context?, intent: Intent?) {
                when (intent?.action) {
                    AudioManager.ACTION_HEADSET_PLUG -> {
                        val state = intent.getIntExtra("state", -1)
                        isHeadsetConnected = state == 1
                        Log.d("HeadsetButton", "Headset connected: $isHeadsetConnected")
                        
                        if (isHeadsetConnected) {
                            // Réactiver la session média quand le casque est connecté
                            mediaSession?.isActive = true
                        }
                    }
                    
                    AudioManager.ACTION_AUDIO_BECOMING_NOISY -> {
                        Log.d("HeadsetButton", "Audio becoming noisy")
                    }
                }
            }
        }
        
        val filter = IntentFilter().apply {
            addAction(AudioManager.ACTION_HEADSET_PLUG)
            addAction(AudioManager.ACTION_AUDIO_BECOMING_NOISY)
        }
        
        context.registerReceiver(headsetReceiver, filter)
    }
    
    private fun checkHeadsetConnection() {
        audioManager?.let { am ->
            isHeadsetConnected = am.isWiredHeadsetOn || am.isBluetoothA2dpOn
            Log.d("HeadsetButton", "Initial headset check: $isHeadsetConnected")
        }
    }
    
    fun isHeadsetConnected(): Boolean {
        audioManager?.let { am ->
            return am.isWiredHeadsetOn || am.isBluetoothA2dpOn
        }
        return false
    }
    
    fun cleanup() {
        mediaSession?.release()
        mediaSession = null
        
        headsetReceiver?.let { receiver ->
            try {
                context.unregisterReceiver(receiver)
            } catch (e: Exception) {
                Log.e("HeadsetButton", "Error unregistering receiver", e)
            }
        }
        headsetReceiver = null
        
        handler.removeCallbacksAndMessages(null)
    }
}