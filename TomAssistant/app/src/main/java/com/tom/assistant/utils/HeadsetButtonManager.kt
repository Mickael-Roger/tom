package com.tom.assistant.utils

import android.content.BroadcastReceiver
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.media.AudioManager
import android.os.Handler
import android.os.Looper
import androidx.media.session.MediaButtonReceiver
import android.support.v4.media.session.MediaSessionCompat
import android.support.v4.media.session.PlaybackStateCompat
import android.support.v4.media.MediaMetadataCompat
import android.app.PendingIntent
import android.content.ComponentName
import android.os.Build
import android.util.Log
import android.view.KeyEvent
import android.widget.Toast

class HeadsetButtonManager(
    private val context: Context,
    private val onToggleRecording: () -> Unit
) {
    
    private var mediaSession: MediaSessionCompat? = null
    private var audioManager: AudioManager? = null
    private var headsetReceiver: BroadcastReceiver? = null
    private var mediaButtonReceiver: BroadcastReceiver? = null
    private var isHeadsetConnected = false
    private val handler = Handler(Looper.getMainLooper())
    
    // Variables pour détecter double-clic
    private var lastClickTime = 0L
    private val DOUBLE_CLICK_TIME_DELTA = 300L // 300ms pour double-clic
    
    fun initialize() {
        audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        Toast.makeText(context, "HeadsetButtonManager: Démarrage...", Toast.LENGTH_SHORT).show()
        
        try {
            setupMediaSession()
            Toast.makeText(context, "HeadsetButtonManager: MediaSession OK", Toast.LENGTH_SHORT).show()
        } catch (e: Exception) {
            Toast.makeText(context, "HeadsetButtonManager: MediaSession ERREUR - ${e.message}", Toast.LENGTH_LONG).show()
            return
        }
        
        // Commentons temporairement le MediaButtonReceiver qui pose problème
        /*
        try {
            setupMediaButtonReceiver()
            Toast.makeText(context, "HeadsetButtonManager: MediaButtonReceiver OK", Toast.LENGTH_SHORT).show()
        } catch (e: Exception) {
            Toast.makeText(context, "HeadsetButtonManager: MediaButtonReceiver ERREUR - ${e.message}", Toast.LENGTH_LONG).show()
        }
        */
        Toast.makeText(context, "MediaButtonReceiver temporairement désactivé", Toast.LENGTH_SHORT).show()
        
        try {
            setupHeadsetReceiver()
            Toast.makeText(context, "HeadsetButtonManager: HeadsetReceiver OK", Toast.LENGTH_SHORT).show()
        } catch (e: Exception) {
            Toast.makeText(context, "HeadsetButtonManager: HeadsetReceiver ERREUR - ${e.message}", Toast.LENGTH_LONG).show()
        }
        
        try {
            checkHeadsetConnection()
            Toast.makeText(context, "HeadsetButtonManager: CheckHeadset OK", Toast.LENGTH_SHORT).show()
        } catch (e: Exception) {
            Toast.makeText(context, "HeadsetButtonManager: CheckHeadset ERREUR - ${e.message}", Toast.LENGTH_LONG).show()
        }
    }
    
    private fun setupMediaSession() {
        Toast.makeText(context, "Configuration MediaSession...", Toast.LENGTH_SHORT).show()
        
        mediaSession = MediaSessionCompat(context, "TomAssistant").apply {
            // Configuration des flags pour recevoir les événements de boutons
            setFlags(
                MediaSessionCompat.FLAG_HANDLES_MEDIA_BUTTONS or
                MediaSessionCompat.FLAG_HANDLES_TRANSPORT_CONTROLS
            )
            
            // Configuration simplifiée - pas de MediaButtonReceiver explicite
            // On compte sur le BroadcastReceiver direct
            
            // État de lecture pour être prioritaire pour les boutons Bluetooth
            setPlaybackState(
                PlaybackStateCompat.Builder()
                    .setActions(
                        PlaybackStateCompat.ACTION_PLAY or
                        PlaybackStateCompat.ACTION_PAUSE or
                        PlaybackStateCompat.ACTION_PLAY_PAUSE or
                        PlaybackStateCompat.ACTION_STOP or
                        PlaybackStateCompat.ACTION_SKIP_TO_NEXT or
                        PlaybackStateCompat.ACTION_SKIP_TO_PREVIOUS
                    )
                    .setState(PlaybackStateCompat.STATE_PLAYING, 0, 1.0f) // PLAYING au lieu de STOPPED
                    .build()
            )
            
            // Métadonnées pour que le système reconnaisse notre app comme lecteur audio
            setMetadata(
                MediaMetadataCompat.Builder()
                    .putString(MediaMetadataCompat.METADATA_KEY_TITLE, "Tom Assistant")
                    .putString(MediaMetadataCompat.METADATA_KEY_ARTIST, "Enregistrement vocal")
                    .putLong(MediaMetadataCompat.METADATA_KEY_DURATION, 0L)
                    .build()
            )
            
            // Callback pour les boutons média
            setCallback(object : MediaSessionCompat.Callback() {
                override fun onMediaButtonEvent(mediaButtonEvent: Intent?): Boolean {
                    Toast.makeText(context, "onMediaButtonEvent appelé!", Toast.LENGTH_SHORT).show()
                    
                    val keyEvent = mediaButtonEvent?.getParcelableExtra<KeyEvent>(Intent.EXTRA_KEY_EVENT)
                    Toast.makeText(context, "KeyEvent: ${keyEvent?.toString()}", Toast.LENGTH_SHORT).show()
                    
                    if (keyEvent?.action == KeyEvent.ACTION_DOWN) {
                        val keyCodeName = when (keyEvent.keyCode) {
                            KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE -> "PLAY_PAUSE"
                            KeyEvent.KEYCODE_HEADSETHOOK -> "HEADSETHOOK"
                            KeyEvent.KEYCODE_MEDIA_PLAY -> "PLAY"
                            KeyEvent.KEYCODE_MEDIA_PAUSE -> "PAUSE"
                            KeyEvent.KEYCODE_MEDIA_NEXT -> "NEXT"
                            KeyEvent.KEYCODE_MEDIA_PREVIOUS -> "PREVIOUS"
                            else -> "UNKNOWN(${keyEvent.keyCode})"
                        }
                        
                        Toast.makeText(context, "Casque: $keyCodeName détecté (ACTION_DOWN)", Toast.LENGTH_LONG).show()
                        
                        // Accepter tous les boutons pour test
                        handleMediaButtonClick(keyCodeName)
                        return true
                    } else if (keyEvent?.action == KeyEvent.ACTION_UP) {
                        Toast.makeText(context, "KeyEvent ACTION_UP ignoré", Toast.LENGTH_SHORT).show()
                    }
                    return super.onMediaButtonEvent(mediaButtonEvent)
                }
                
                override fun onPlay() {
                    Toast.makeText(context, "Casque: onPlay() appelé", Toast.LENGTH_SHORT).show()
                    handleMediaButtonClick("onPlay")
                }
                
                override fun onPause() {
                    Toast.makeText(context, "Casque: onPause() appelé", Toast.LENGTH_SHORT).show()
                    handleMediaButtonClick("onPause")
                }
                
                override fun onPlayFromSearch(query: String?, extras: android.os.Bundle?) {
                    Toast.makeText(context, "Casque: onPlayFromSearch() appelé", Toast.LENGTH_SHORT).show()
                    handleMediaButtonClick("onPlayFromSearch")
                }
            })
            
            isActive = true
        }
        
        // Forcer la MediaSession à être reconnue comme lecteur actif
        Handler(Looper.getMainLooper()).postDelayed({
            mediaSession?.setPlaybackState(
                PlaybackStateCompat.Builder()
                    .setActions(
                        PlaybackStateCompat.ACTION_PLAY or
                        PlaybackStateCompat.ACTION_PAUSE or
                        PlaybackStateCompat.ACTION_PLAY_PAUSE or
                        PlaybackStateCompat.ACTION_STOP or
                        PlaybackStateCompat.ACTION_SKIP_TO_NEXT or
                        PlaybackStateCompat.ACTION_SKIP_TO_PREVIOUS
                    )
                    .setState(PlaybackStateCompat.STATE_PLAYING, 0, 1.0f)
                    .build()
            )
            Toast.makeText(context, "MediaSession forcée en état PLAYING", Toast.LENGTH_SHORT).show()
        }, 1000)
        
        // Force l'acquisition du focus audio pour les boutons média
        val result = audioManager?.requestAudioFocus(
            { focusChange ->
                Toast.makeText(context, "AudioFocus changé: $focusChange", Toast.LENGTH_SHORT).show()
            }, 
            AudioManager.STREAM_MUSIC, 
            AudioManager.AUDIOFOCUS_GAIN // Gain permanent au lieu de transitoire
        )
        Toast.makeText(context, "MediaSession active, AudioFocus: ${if (result == AudioManager.AUDIOFOCUS_REQUEST_GRANTED) "OK" else "FAILED($result)"}", Toast.LENGTH_LONG).show()
    }
    
    private fun setupMediaButtonReceiver() {
        try {
            mediaButtonReceiver = object : BroadcastReceiver() {
                override fun onReceive(context: Context?, intent: Intent?) {
                    try {
                        Toast.makeText(context, "MediaButton broadcast reçu!", Toast.LENGTH_SHORT).show()
                        if (Intent.ACTION_MEDIA_BUTTON == intent?.action) {
                            val keyEvent = intent.getParcelableExtra<KeyEvent>(Intent.EXTRA_KEY_EVENT)
                            if (keyEvent?.action == KeyEvent.ACTION_DOWN) {
                                Toast.makeText(context, "Bouton média direct: ${keyEvent.keyCode}", Toast.LENGTH_SHORT).show()
                                handleMediaButtonClick("DirectBroadcast")
                            }
                        }
                    } catch (e: Exception) {
                        Toast.makeText(context, "Erreur dans MediaButton onReceive: ${e.message}", Toast.LENGTH_SHORT).show()
                    }
                }
            }
            
            val mediaFilter = IntentFilter(Intent.ACTION_MEDIA_BUTTON)
            mediaFilter.priority = 1000  // Haute priorité
            context.registerReceiver(mediaButtonReceiver, mediaFilter)
            Toast.makeText(context, "MediaButtonReceiver enregistré", Toast.LENGTH_SHORT).show()
        } catch (e: Exception) {
            Toast.makeText(context, "Erreur setup MediaButtonReceiver: ${e.message}", Toast.LENGTH_LONG).show()
            throw e
        }
    }
    
    private fun handleMediaButtonClick(source: String = "unknown") {
        val currentTime = System.currentTimeMillis()
        
        Toast.makeText(context, "Casque: handleMediaButtonClick($source)", Toast.LENGTH_SHORT).show()
        
        if (currentTime - lastClickTime < DOUBLE_CLICK_TIME_DELTA) {
            // Double-clic détecté - ignorer car on ne veut qu'un simple clic
            Toast.makeText(context, "Casque: Double-clic ignoré", Toast.LENGTH_SHORT).show()
            return
        }
        
        lastClickTime = currentTime
        
        // Attendre un peu pour s'assurer qu'il n'y a pas de double-clic
        handler.postDelayed({
            if (System.currentTimeMillis() - lastClickTime >= DOUBLE_CLICK_TIME_DELTA - 50) {
                Log.d("HeadsetButton", "Media button clicked - toggling recording")
                Toast.makeText(context, "Casque: Déclenchement enregistrement!", Toast.LENGTH_SHORT).show()
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
                        Toast.makeText(context, "Casque filaire: ${if (isHeadsetConnected) "Connecté" else "Déconnecté"}", Toast.LENGTH_SHORT).show()
                        
                        if (isHeadsetConnected) {
                            // Réactiver la session média quand le casque est connecté
                            mediaSession?.isActive = true
                        }
                    }
                    
                    AudioManager.ACTION_AUDIO_BECOMING_NOISY -> {
                        Log.d("HeadsetButton", "Audio becoming noisy")
                    }
                    
                    // Cas Bluetooth temporairement commentés
                    /*
                    BluetoothDevice.ACTION_ACL_CONNECTED -> {
                        Toast.makeText(context, "Bluetooth connecté", Toast.LENGTH_SHORT).show()
                        checkHeadsetConnection()
                    }
                    
                    BluetoothDevice.ACTION_ACL_DISCONNECTED -> {
                        Toast.makeText(context, "Bluetooth déconnecté", Toast.LENGTH_SHORT).show()
                        checkHeadsetConnection()
                    }
                    */
                }
            }
        }
        
        val filter = IntentFilter().apply {
            addAction(AudioManager.ACTION_HEADSET_PLUG)
            addAction(AudioManager.ACTION_AUDIO_BECOMING_NOISY)
            // Actions Bluetooth temporairement désactivées pour éviter les crashes
            // addAction(BluetoothDevice.ACTION_ACL_CONNECTED)
            // addAction(BluetoothDevice.ACTION_ACL_DISCONNECTED)
            // addAction(BluetoothAdapter.ACTION_CONNECTION_STATE_CHANGED)
            // addAction("android.bluetooth.a2dp.profile.action.CONNECTION_STATE_CHANGED")
            // addAction("android.bluetooth.headset.profile.action.CONNECTION_STATE_CHANGED")
        }
        
        context.registerReceiver(headsetReceiver, filter)
    }
    
    private fun checkHeadsetConnection() {
        audioManager?.let { am ->
            val wiredConnected = am.isWiredHeadsetOn
            val bluetoothConnected = am.isBluetoothA2dpOn
            isHeadsetConnected = wiredConnected || bluetoothConnected
            Log.d("HeadsetButton", "Initial headset check: $isHeadsetConnected (wired: $wiredConnected, bluetooth: $bluetoothConnected)")
            
            val connectionType = when {
                wiredConnected -> "filaire"
                bluetoothConnected -> "Bluetooth"
                else -> "aucun"
            }
            Toast.makeText(context, "Casque initial: $connectionType", Toast.LENGTH_LONG).show()
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
                Log.e("HeadsetButton", "Error unregistering headset receiver", e)
            }
        }
        headsetReceiver = null
        
        mediaButtonReceiver?.let { receiver ->
            try {
                context.unregisterReceiver(receiver)
            } catch (e: Exception) {
                Log.e("HeadsetButton", "Error unregistering media button receiver", e)
            }
        }
        mediaButtonReceiver = null
        
        handler.removeCallbacksAndMessages(null)
    }
}