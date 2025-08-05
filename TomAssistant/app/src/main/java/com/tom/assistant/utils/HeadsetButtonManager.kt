package com.tom.assistant.utils

import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.media.MediaPlayer
import android.media.session.MediaSession
import android.media.session.PlaybackState
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.KeyEvent
import android.widget.Toast

class HeadsetButtonManager(
    private val context: Context,
    private val onToggleRecording: () -> Unit
) {
    
    private var mediaSession: MediaSession? = null
    private var audioManager: AudioManager? = null
    private var mediaPlayer: MediaPlayer? = null
    private var audioFocusRequest: AudioFocusRequest? = null
    private val handler = Handler(Looper.getMainLooper())
    
    // Variables pour détecter double-clic
    private var lastClickTime = 0L
    private val DOUBLE_CLICK_TIME_DELTA = 300L // 300ms pour double-clic
    
    fun initialize() {
        audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        Log.d("HeadsetButtonManager", "Initializing HeadsetButtonManager...")
        
        setupMediaSession()
        requestAudioFocusAndPlay()
    }
    
    private fun setupMediaSession() {
        Log.d("HeadsetButtonManager", "Setting up MediaSession...")
        
        mediaSession = MediaSession(context, "TomAssistant").apply {
            @Suppress("DEPRECATION")
            setFlags(MediaSession.FLAG_HANDLES_MEDIA_BUTTONS)

            val stateBuilder = PlaybackState.Builder()
                .setActions(PlaybackState.ACTION_PLAY or PlaybackState.ACTION_PAUSE or PlaybackState.ACTION_PLAY_PAUSE)
            setPlaybackState(stateBuilder.build())

            setCallback(object : MediaSession.Callback() {
                override fun onPlay() {
                    Log.d("HeadsetButtonManager", "onPlay() called - triggering speech-to-text")
                    handleMediaButtonClick()
                }
                
                override fun onPause() {
                    Log.d("HeadsetButtonManager", "onPause() called - triggering speech-to-text")
                    handleMediaButtonClick()
                }
                
                override fun onMediaButtonEvent(mediaButtonEvent: Intent): Boolean {
                    val event = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                        mediaButtonEvent.getParcelableExtra(Intent.EXTRA_KEY_EVENT, KeyEvent::class.java)
                    } else {
                        @Suppress("DEPRECATION")
                        mediaButtonEvent.getParcelableExtra<KeyEvent>(Intent.EXTRA_KEY_EVENT)
                    }
                    Log.d("HeadsetButtonManager", "onMediaButtonEvent: $event")
                    
                    if (event != null && event.action == KeyEvent.ACTION_DOWN) {
                        val keyCode = event.keyCode
                        if (keyCode == KeyEvent.KEYCODE_MEDIA_PLAY || keyCode == KeyEvent.KEYCODE_MEDIA_PAUSE || keyCode == KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE) {
                            Log.d("HeadsetButtonManager", "Bluetooth button pressed - triggering speech-to-text")
                            handleMediaButtonClick()
                            return true
                        }
                    }
                    return super.onMediaButtonEvent(mediaButtonEvent)
                }
            })
            isActive = true
        }
        
        Log.d("HeadsetButtonManager", "MediaSession configured and active.")
    }
    
    private fun requestAudioFocusAndPlay() {
        Log.d("HeadsetButtonManager", "Requesting audio focus...")
        
        val audioAttributes = AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_MEDIA)
            .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
            .build()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            audioFocusRequest = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
                .setAudioAttributes(audioAttributes)
                .setOnAudioFocusChangeListener { focusChange ->
                    Log.d("HeadsetButtonManager", "onAudioFocusChange: $focusChange")
                }
                .build()
            
            val focusResult = audioManager?.requestAudioFocus(audioFocusRequest!!)
            if (focusResult == AudioManager.AUDIOFOCUS_REQUEST_GRANTED) {
                Log.d("HeadsetButtonManager", "Audio focus granted.")
                startSilentPlayback()
            }
        } else {
            @Suppress("DEPRECATION")
            val focusResult = audioManager?.requestAudioFocus(
                { focusChange -> 
                    Log.d("HeadsetButtonManager", "onAudioFocusChange: $focusChange")
                }, 
                AudioManager.STREAM_MUSIC, 
                AudioManager.AUDIOFOCUS_GAIN
            )
            if (focusResult == AudioManager.AUDIOFOCUS_REQUEST_GRANTED) {
                Log.d("HeadsetButtonManager", "Audio focus granted (legacy method).")
                startSilentPlayback()
            }
        }
    }

    private fun startSilentPlayback() {
        try {
            val resourceId = context.resources.getIdentifier("silent", "raw", context.packageName)
            if (resourceId != 0) {
                mediaPlayer = MediaPlayer.create(context, resourceId)?.apply {
                    isLooping = true
                    start()
                    Log.d("HeadsetButtonManager", "Silent playback started.")
                }
            } else {
                Log.e("HeadsetButtonManager", "Silent.mp3 resource not found in res/raw")
            }
        } catch (e: Exception) {
            Log.e("HeadsetButtonManager", "Error starting silent playback: ${e.message}")
        }
    }

    private fun handleMediaButtonClick() {
        val currentTime = System.currentTimeMillis()
        Log.d("HeadsetButtonManager", "handleMediaButtonClick called")
        
        if (currentTime - lastClickTime < DOUBLE_CLICK_TIME_DELTA) {
            Log.d("HeadsetButtonManager", "Double-click detected - ignoring")
            return
        }
        
        lastClickTime = currentTime
        
        // Attendre un peu pour s'assurer qu'il n'y a pas de double-clic
        handler.postDelayed({
            if (System.currentTimeMillis() - lastClickTime >= DOUBLE_CLICK_TIME_DELTA - 50) {
                Log.d("HeadsetButtonManager", "Media button clicked - triggering recording")
                onToggleRecording()
            }
        }, DOUBLE_CLICK_TIME_DELTA + 50)
    }
    
    private fun abandonAudioFocus() {
        Log.d("HeadsetButtonManager", "Abandoning audio focus.")
        
        mediaPlayer?.let {
            if (it.isPlaying) {
                it.stop()
            }
            it.release()
            mediaPlayer = null
        }
        
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            audioFocusRequest?.let {
                audioManager?.abandonAudioFocusRequest(it)
            }
        } else {
            @Suppress("DEPRECATION")
            audioManager?.abandonAudioFocus { }
        }
    }
    
    fun cleanup() {
        Log.d("HeadsetButtonManager", "Cleaning up resources.")
        
        mediaSession?.release()
        mediaSession = null
        
        abandonAudioFocus()
        
        handler.removeCallbacksAndMessages(null)
    }
}