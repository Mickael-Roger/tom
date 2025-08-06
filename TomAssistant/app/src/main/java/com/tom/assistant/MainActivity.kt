package com.tom.assistant

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.location.Location
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.Toast
import android.animation.ObjectAnimator
import android.view.animation.LinearInterpolator
import android.view.GestureDetector
import android.view.MotionEvent
import android.view.KeyEvent
import android.util.Log
import kotlin.math.abs
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.google.android.gms.location.FusedLocationProviderClient
import com.google.android.gms.location.LocationServices
import com.tom.assistant.databinding.ActivityMainBinding
import com.tom.assistant.models.*
import com.tom.assistant.network.ApiClient
import com.tom.assistant.ui.auth.LoginActivity
import com.tom.assistant.ui.chat.ChatAdapter
import com.tom.assistant.ui.tasks.TasksAdapter
import com.tom.assistant.utils.AudioManager
import com.tom.assistant.utils.SessionManager
import com.tom.assistant.utils.HeadsetButtonManager
import io.noties.markwon.Markwon
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import retrofit2.HttpException
import java.io.IOException
import java.util.regex.Pattern

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var sessionManager: SessionManager
    private lateinit var chatAdapter: ChatAdapter
    private lateinit var tasksAdapter: TasksAdapter
    private lateinit var audioManager: AudioManager
    private lateinit var fusedLocationClient: FusedLocationProviderClient
    private lateinit var headsetButtonManager: HeadsetButtonManager

    private var currentPosition: Position? = null
    private var lastDisplayedTaskId = 0
    private var isSettingsPanelVisible = false
    private var isTasksPanelVisible = false
    private var tickerAnimator: ObjectAnimator? = null

    companion object {
        private const val PERMISSION_REQUEST_CODE = 1001
        private val REQUIRED_PERMISSIONS = arrayOf(
            Manifest.permission.RECORD_AUDIO,
            Manifest.permission.ACCESS_FINE_LOCATION,
            Manifest.permission.ACCESS_COARSE_LOCATION
        )
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        // Empêcher la mise en veille de l'écran
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        // Initialiser ApiClient avec le contexte pour les cookies persistants
        ApiClient.initialize(this)
        
        sessionManager = SessionManager(this)
        
        // Vérifier la session locale puis avec le serveur
        if (!sessionManager.isLoggedIn()) {
            navigateToLogin()
            return
        }

        setupToolbar()
        setupRecyclerViews()
        setupButtons()
        setupAudio()
        setupHeadsetButtons()
        setupLocation()
        setupPermissions()
        
        // Démarrer le service média pour maintenir la MediaSession active
        startService(Intent(this, MediaService::class.java))
        
        // Charger les paramètres
        loadSettings()
        
        // Démarrer les tâches périodiques
        startPeriodicTasks()
        
        // Tester la session avec le serveur (silencieusement)
        testSessionValidityQuietly()
        
        // Test du ticker avec des données de test
        testTickerWithDummyData()
    }

    private fun setupToolbar() {
        // Toolbar supprimée pour plus d'espace
    }

    private fun setupRecyclerViews() {
        // Chat RecyclerView
        val markwon = Markwon.create(this)
        chatAdapter = ChatAdapter(markwon)
        binding.rvChat.apply {
            layoutManager = LinearLayoutManager(this@MainActivity)
            adapter = chatAdapter
        }

        // Tasks RecyclerView
        tasksAdapter = TasksAdapter()
        binding.rvTasks.apply {
            layoutManager = LinearLayoutManager(this@MainActivity)
            adapter = tasksAdapter
        }
    }

    private fun setupButtons() {
        // Message input listener
        binding.etMessage.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: Editable?) {
                binding.btnSend.isEnabled = !s.isNullOrBlank()
            }
        })

        // Send button
        binding.btnSend.setOnClickListener {
            sendMessage()
        }

        // Voice button
        binding.btnVoice.setOnClickListener {
            if (checkAudioPermission()) {
                startVoiceInput()
            } else {
                requestPermissions()
            }
        }

        // Reset button - different behavior for debug/release
        if (BuildConfig.DEBUG) {
            // Debug: visible button
            binding.btnReset.visibility = View.VISIBLE
            binding.btnReset.setOnClickListener {
                resetConversation()
            }
        } else {
            // Release: hidden button, slide gesture instead
            binding.btnReset.visibility = View.GONE
            setupResetSlideGesture()
        }

        // Settings button (header)
        binding.ivSettingsHeader.setOnClickListener {
            toggleSettingsPanel()
        }

        // Tasks button (header)
        binding.ivTasksHeader.setOnClickListener {
            toggleTasksPanel()
        }

        // Sound switch
        binding.switchSound.setOnCheckedChangeListener { _, isChecked ->
            sessionManager.saveSoundEnabled(isChecked)
        }

        // Auto-submit switch
        binding.switchAutoSubmit.setOnCheckedChangeListener { _, isChecked ->
            sessionManager.saveAutoSubmitEnabled(isChecked)
        }

        // Logout button
        binding.btnLogout.setOnClickListener {
            logout()
        }

        // Overlay background - fermer les panneaux en cliquant dessus
        binding.overlayBackground.setOnClickListener {
            closeAllPanels()
        }
    }

    private fun setupResetSlideGesture() {
        val gestureDetector = GestureDetector(this, object : GestureDetector.SimpleOnGestureListener() {
            override fun onFling(
                e1: MotionEvent?,
                e2: MotionEvent,
                velocityX: Float,
                velocityY: Float
            ): Boolean {
                if (e1 != null) {
                    val diffY = e2.y - e1.y
                    val diffX = e2.x - e1.x
                    
                    // Slide from bottom to top
                    if (abs(diffY) > abs(diffX) && diffY < -100 && abs(velocityY) > 100) {
                        resetConversation()
                        return true
                    }
                }
                return false
            }
        })
        
        // Apply gesture to the main chat area
        binding.rvChat.setOnTouchListener { _, event ->
            gestureDetector.onTouchEvent(event)
            false // Allow normal scroll behavior
        }
    }

    private fun setupAudio() {
        audioManager = AudioManager(
            context = this,
            onSpeechResult = { result ->
                binding.etMessage.setText(result)
                if (sessionManager.isAutoSubmitEnabled()) {
                    sendMessage()
                }
            },
            onSpeechError = { error ->
                Toast.makeText(this, "Speech error: $error", Toast.LENGTH_SHORT).show()
            }
        )
    }
    
    private fun setupHeadsetButtons() {
        headsetButtonManager = HeadsetButtonManager(
            context = this,
            onToggleRecording = {
                // Vérifier les permissions avant d'utiliser l'audio
                if (checkAudioPermission()) {
                    toggleVoiceInputFromHeadset()
                } else {
                    Toast.makeText(this, "Microphone permission required", Toast.LENGTH_SHORT).show()
                }
            }
        )
        headsetButtonManager.initialize()
    }
    
    private fun toggleVoiceInputFromHeadset() {
        audioManager.stopSpeaking() // Arrêter le TTS d'abord
        
        if (audioManager.isCurrentlyListening()) {
            // Arrêter l'enregistrement
            audioManager.stopListening()
            // Remettre le bouton voice à l'état normal
            binding.btnVoice.setBackgroundResource(android.R.drawable.ic_btn_speak_now)
        } else {
            // Démarrer l'enregistrement
            audioManager.startListening()
            // Changer la couleur du bouton pendant l'écoute
            binding.btnVoice.setBackgroundResource(R.drawable.voice_button_background)
        }
    }

    private fun setupLocation() {
        fusedLocationClient = LocationServices.getFusedLocationProviderClient(this)
        updateLocation()
    }

    private fun setupPermissions() {
        if (!hasAllPermissions()) {
            requestPermissions()
        }
    }

    private fun hasAllPermissions(): Boolean {
        return REQUIRED_PERMISSIONS.all { permission ->
            ContextCompat.checkSelfPermission(this, permission) == PackageManager.PERMISSION_GRANTED
        }
    }

    private fun checkAudioPermission(): Boolean {
        return ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
    }

    private fun requestPermissions() {
        ActivityCompat.requestPermissions(this, REQUIRED_PERMISSIONS, PERMISSION_REQUEST_CODE)
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == PERMISSION_REQUEST_CODE) {
            updateLocation()
        }
    }

    private fun updateLocation() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED) {
            fusedLocationClient.lastLocation.addOnSuccessListener { location: Location? ->
                location?.let {
                    currentPosition = Position(it.latitude, it.longitude)
                }
            }
        }
    }

    private fun loadSettings() {
        binding.switchSound.isChecked = sessionManager.isSoundEnabled()
        binding.switchAutoSubmit.isChecked = sessionManager.isAutoSubmitEnabled()
    }

    private fun startVoiceInput() {
        audioManager.stopSpeaking()
        audioManager.startListening()
        
        // Changer la couleur du bouton pendant l'écoute
        binding.btnVoice.setBackgroundResource(R.drawable.voice_button_background)
    }

    private fun sendMessage() {
        val message = binding.etMessage.text.toString().trim()
        if (message.isEmpty()) return

        // Ajouter le message utilisateur au chat
        chatAdapter.addMessage(ChatMessage(message, true))
        scrollToBottom()

        // Créer la requête
        val request = ProcessRequest(
            request = message,
            position = currentPosition,
            sound_enabled = sessionManager.isSoundEnabled(),
            client_type = "android"
        )

        // Envoyer la requête
        lifecycleScope.launch {
            try {
                val response = ApiClient.tomApiService.process(request)
                if (response.isSuccessful) {
                    response.body()?.let { processResponse ->
                        // Ajouter la réponse au chat
                        chatAdapter.addMessage(ChatMessage(processResponse.response, false))
                        scrollToBottom()

                        // Traiter les commandes personnalisées
                        processCustomCommands(processResponse.response)

                        // Lire la réponse avec TTS si activé
                        if (sessionManager.isSoundEnabled()) {
                            // Utiliser response_tts si disponible (synthétisé par le serveur), sinon fallback
                            val textToSpeak = processResponse.response_tts ?: cleanTextForTTS(processResponse.response)
                            audioManager.speak(textToSpeak)
                        }
                    }
                } else {
                    if (response.code() == 302 || response.code() == 401 || response.code() == 403) {
                        sessionManager.logout()
                        navigateToLogin()
                        return@launch
                    }
                    showError("Error: ${response.code()}")
                    resetConversation()
                }
            } catch (e: IOException) {
                showError("Network error")
                resetConversation()
            } catch (e: HttpException) {
                showError("HTTP error: ${e.code()}")
                resetConversation()
            } catch (e: Exception) {
                showError("Error: ${e.message}")
                resetConversation()
            }
        }

        // Vider le champ de saisie
        binding.etMessage.setText("")
    }

    private fun processCustomCommands(text: String) {
        // Traiter les commandes [open:URL]
        val openPattern = Pattern.compile("\\[open:(.+?)\\]")
        val matcher = openPattern.matcher(text)
        
        while (matcher.find()) {
            val url = matcher.group(1)
            if (url != null && isValidUrl(url)) {
                // Ouvrir l'URL dans le navigateur
                val intent = Intent(Intent.ACTION_VIEW, android.net.Uri.parse(url))
                if (intent.resolveActivity(packageManager) != null) {
                    startActivity(intent)
                }
            }
        }
    }

    private fun isValidUrl(url: String): Boolean {
        return try {
            java.net.URL(url)
            true
        } catch (e: Exception) {
            false
        }
    }

    private fun cleanTextForTTS(text: String): String {
        // Supprimer les commandes markdown et personnalisées
        return text
            .replace(Regex("\\[open:.*?\\]"), "")
            .replace(Regex("\\*\\*(.*?)\\*\\*"), "$1") // Gras
            .replace(Regex("\\*(.*?)\\*"), "$1") // Italique
            .replace(Regex("```[\\s\\S]*?```"), "") // Blocs de code
            .replace(Regex("`(.*?)`"), "$1") // Code inline
            .trim()
    }

    private fun testSessionValidityQuietly() {
        lifecycleScope.launch {
            try {
                // Test silencieux avec getTasks qui ne modifie rien
                val response = ApiClient.tomApiService.getTasks()
                if (response.isSuccessful) {
                    // Session valide, charger les données
                    response.body()?.let { tasksResponse ->
                        tasksAdapter.updateTasks(tasksResponse.background_tasks)
                        updateTasksCounter(tasksResponse.background_tasks.size)
                    }
                } else {
                    // Session invalide, retourner au login
                    if (response.code() == 302 || response.code() == 401 || response.code() == 403 || response.code() == 500) {
                        sessionManager.logout()
                        navigateToLogin()
                    }
                }
            } catch (e: Exception) {
                // En cas d'erreur de connexion, on reste sur l'interface
                // mais on ne redirige pas automatiquement vers login
            }
        }
    }

    private fun testSessionAndReset() {
        lifecycleScope.launch {
            try {
                val response = ApiClient.tomApiService.reset()
                if (response.isSuccessful) {
                    chatAdapter.clearMessages()
                    fetchTasks()
                } else {
                    // Session invalide, retourner au login
                    if (response.code() == 302 || response.code() == 401 || response.code() == 403 || response.code() == 500) {
                        sessionManager.logout()
                        navigateToLogin()
                        return@launch
                    }
                    showError("Reset failed: ${response.code()}")
                }
            } catch (e: Exception) {
                showError("Session test error: ${e.message}")
                // En cas d'erreur de session, rediriger vers login
                sessionManager.logout()
                navigateToLogin()
            }
        }
    }
    
    private fun resetConversation() {
        lifecycleScope.launch {
            try {
                val response = ApiClient.tomApiService.reset()
                if (response.isSuccessful) {
                    chatAdapter.clearMessages()
                    fetchTasks()
                } else {
                    if (response.code() == 302 || response.code() == 401 || response.code() == 403) {
                        sessionManager.logout()
                        navigateToLogin()
                        return@launch
                    }
                    showError("Reset failed: ${response.code()}")
                }
            } catch (e: Exception) {
                showError("Reset error: ${e.message}")
            }
        }
    }

    private fun fetchTasks() {
        lifecycleScope.launch {
            try {
                val response = ApiClient.tomApiService.getTasks()
                if (response.isSuccessful) {
                    response.body()?.let { tasksResponse ->
                        // Mettre à jour la liste des tâches
                        tasksAdapter.updateTasks(tasksResponse.background_tasks)
                        updateTasksCounter(tasksResponse.background_tasks.size)
                        
                        // Mettre à jour l'ID uniquement (sans affichage dans le chat)
                        if (tasksResponse.id > lastDisplayedTaskId) {
                            lastDisplayedTaskId = tasksResponse.id
                        }
                    }
                }
            } catch (e: Exception) {
                // Ignorer les erreurs de tâches en arrière-plan
            }
        }
    }

    private fun startPeriodicTasks() {
        // Mettre à jour la position toutes les 30 secondes
        lifecycleScope.launch {
            while (isActive) {
                delay(30000)
                updateLocation()
            }
        }

        // Récupérer les tâches toutes les 60 secondes
        lifecycleScope.launch {
            while (isActive) {
                delay(60000)
                fetchTasks()
            }
        }
    }

    private fun updateTasksCounter(count: Int) {
        binding.tvTasksCounterHeader.text = count.toString()
        binding.tvTasksCounterHeader.visibility = if (count > 0) View.VISIBLE else View.GONE
        
        // Update notification ticker
        updateNotificationTicker()
    }

    private fun updateNotificationTicker() {
        Log.d("TomTicker", "updateNotificationTicker called")
        lifecycleScope.launch {
            try {
                val response = ApiClient.tomApiService.getTasks()
                if (response.isSuccessful) {
                    response.body()?.let { tasksResponse ->
                        val notifications = tasksResponse.background_tasks
                        Log.d("TomTicker", "Got ${notifications.size} notifications")
                        
                        if (notifications.isEmpty()) {
                            binding.tvNotificationTicker.text = "Aucune notification"
                            Log.d("TomTicker", "No notifications - showing default text")
                        } else {
                            // Create scrolling text with bold module names
                            val notificationText = notifications.joinToString("    •    ") { task ->
                                "${task.module}: ${task.status}"
                            } + "     " // Ajout d'espaces à la fin pour éviter la troncature
                            
                            Log.d("TomTicker", "Original notification text length: ${notificationText.length}")
                            Log.d("TomTicker", "Original notification text: '$notificationText'")
                            
                            binding.tvNotificationTicker.text = notificationText
                            
                            // Check what was actually set
                            val actualSetText = binding.tvNotificationTicker.text.toString()
                            Log.d("TomTicker", "Actually set text length: ${actualSetText.length}")
                            Log.d("TomTicker", "Actually set text: '$actualSetText'")
                            
                            if (notificationText != actualSetText) {
                                Log.e("TomTicker", "TEXT WAS TRUNCATED SOMEWHERE!")
                                Log.e("TomTicker", "Expected: '$notificationText'")
                                Log.e("TomTicker", "Got: '$actualSetText'")
                            }
                            
                            // Start scrolling animation
                            startTickerAnimation()
                        }
                    }
                } else {
                    Log.e("TomTicker", "API response failed: ${response.code()}")
                }
            } catch (e: Exception) {
                Log.e("TomTicker", "Error updating ticker: ${e.message}")
            }
        }
    }

    private fun startTickerAnimation() {
        Log.d("TomTicker", "startTickerAnimation called")
        val ticker = binding.tvNotificationTicker
        val container = ticker.parent as? ViewGroup
        
        // Cancel existing animation
        tickerAnimator?.cancel()
        Log.d("TomTicker", "Cancelled existing animation")
        
        // Wait for layout to complete, then start animation
        ticker.post {
            // Reset position
            ticker.translationX = 0f
            
            // Measure the actual text content width including padding
            val paint = ticker.paint
            val textContent = ticker.text.toString()
            val actualTextWidth = paint.measureText(textContent)
            val paddingWidth = ticker.paddingStart + ticker.paddingEnd
            val totalTextWidth = actualTextWidth + paddingWidth
            val containerWidth = container?.width ?: 0
            
            Log.d("TomTicker", "Text: '$textContent'")
            Log.d("TomTicker", "Actual text width: $actualTextWidth, Padding: $paddingWidth, Total: $totalTextWidth")
            Log.d("TomTicker", "Container width: $containerWidth")
            
            if (totalTextWidth > containerWidth && containerWidth > 0) {
                // Force the TextView to use its actual text width
                val newWidth = totalTextWidth.toInt()
                val widthSpec = View.MeasureSpec.makeMeasureSpec(newWidth, View.MeasureSpec.EXACTLY)
                val heightSpec = View.MeasureSpec.makeMeasureSpec(ticker.height, View.MeasureSpec.EXACTLY)
                ticker.measure(widthSpec, heightSpec)
                ticker.layout(0, 0, newWidth, ticker.height)
                
                Log.d("TomTicker", "TextView resized to: ${ticker.width} x ${ticker.height}")
                
                // Start scrolling animation from right edge of container to left edge
                val startX = containerWidth.toFloat()
                val endX = -newWidth.toFloat()
                val distance = startX - endX
                
                Log.d("TomTicker", "Starting animation: startX=$startX, endX=$endX, distance=$distance")
                
                tickerAnimator = ObjectAnimator.ofFloat(ticker, "translationX", startX, endX).apply {
                    duration = (distance * 10).toLong() // 10ms per pixel for smoother animation
                    interpolator = LinearInterpolator()
                    repeatCount = ObjectAnimator.INFINITE
                    repeatMode = ObjectAnimator.RESTART
                    start()
                }
                Log.d("TomTicker", "Animation started with duration: ${(distance * 10).toLong()}ms")
            } else {
                // Text fits in container, center it
                ticker.translationX = 0f
                Log.d("TomTicker", "Text fits in container, no animation needed")
            }
        }
    }

    private fun toggleSettingsPanel() {
        isSettingsPanelVisible = !isSettingsPanelVisible
        binding.settingsPanel.visibility = if (isSettingsPanelVisible) View.VISIBLE else View.GONE
        binding.overlayBackground.visibility = if (isSettingsPanelVisible) View.VISIBLE else View.GONE
        
        if (isSettingsPanelVisible && isTasksPanelVisible) {
            isTasksPanelVisible = false
            binding.tasksPanel.visibility = View.GONE
        }
    }

    private fun toggleTasksPanel() {
        isTasksPanelVisible = !isTasksPanelVisible
        binding.tasksPanel.visibility = if (isTasksPanelVisible) View.VISIBLE else View.GONE
        binding.overlayBackground.visibility = if (isTasksPanelVisible) View.VISIBLE else View.GONE
        
        if (isTasksPanelVisible && isSettingsPanelVisible) {
            isSettingsPanelVisible = false
            binding.settingsPanel.visibility = View.GONE
        }
    }

    private fun closeAllPanels() {
        isSettingsPanelVisible = false
        isTasksPanelVisible = false
        binding.settingsPanel.visibility = View.GONE
        binding.tasksPanel.visibility = View.GONE
        binding.overlayBackground.visibility = View.GONE
    }

    private fun logout() {
        sessionManager.logout()
        navigateToLogin()
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        val keyName = when (keyCode) {
            KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE -> "MEDIA_PLAY_PAUSE"
            KeyEvent.KEYCODE_HEADSETHOOK -> "HEADSETHOOK" 
            KeyEvent.KEYCODE_MEDIA_PLAY -> "MEDIA_PLAY"
            KeyEvent.KEYCODE_MEDIA_PAUSE -> "MEDIA_PAUSE"
            KeyEvent.KEYCODE_MEDIA_NEXT -> "MEDIA_NEXT"
            KeyEvent.KEYCODE_MEDIA_PREVIOUS -> "MEDIA_PREVIOUS"
            KeyEvent.KEYCODE_VOLUME_UP -> "VOLUME_UP"
            KeyEvent.KEYCODE_VOLUME_DOWN -> "VOLUME_DOWN"
            else -> "OTHER($keyCode)"
        }
        
        // Log de debug pour voir TOUS les événements clavier
        Log.d("MainActivity", "onKeyDown: keyCode=$keyCode, keyName=$keyName, event=$event")
        
        // Si c'est un bouton média, déclencher l'enregistrement vocal
        when (keyCode) {
            KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE,
            KeyEvent.KEYCODE_HEADSETHOOK,
            KeyEvent.KEYCODE_MEDIA_PLAY,
            KeyEvent.KEYCODE_MEDIA_PAUSE -> {
                Log.d("MainActivity", "Bluetooth headset button pressed - triggering voice input")
                toggleVoiceInputFromHeadset()
                return true
            }
        }
        
        return super.onKeyDown(keyCode, event)
    }

    private fun navigateToLogin() {
        val intent = Intent(this, LoginActivity::class.java)
        intent.flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        startActivity(intent)
        finish()
    }

    private fun scrollToBottom() {
        binding.rvChat.scrollToPosition(chatAdapter.itemCount - 1)
    }

    private fun showError(message: String) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
    }

    private fun testTickerWithDummyData() {
        Log.d("TomTicker", "Testing ticker with dummy data")
        
        // Simulate long notification text that should scroll
        val longText = "Module1: Status très long qui devrait défiler    •    Module2: Autre status long    •    Module3: Encore plus de texte"
        binding.tvNotificationTicker.text = longText
        
        // Wait a bit for layout then start animation
        binding.tvNotificationTicker.postDelayed({
            startTickerAnimation()
        }, 500)
    }

    override fun onDestroy() {
        super.onDestroy()
        audioManager.destroy()
        headsetButtonManager.cleanup()
        tickerAnimator?.cancel()
    }
}