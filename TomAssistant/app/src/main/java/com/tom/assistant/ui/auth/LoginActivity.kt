package com.tom.assistant.ui.auth

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.tom.assistant.MainActivity
import com.tom.assistant.databinding.ActivityLoginBinding
import com.tom.assistant.network.ApiClient
import com.tom.assistant.utils.SessionManager
import kotlinx.coroutines.launch
import retrofit2.HttpException
import java.io.IOException

class LoginActivity : AppCompatActivity() {
    
    private lateinit var binding: ActivityLoginBinding
    private lateinit var sessionManager: SessionManager
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityLoginBinding.inflate(layoutInflater)
        setContentView(binding.root)
        
        // Initialiser ApiClient avec le contexte pour les cookies persistants
        ApiClient.initialize(this)
        
        sessionManager = SessionManager(this)
        
        // Vérifier si l'utilisateur est déjà connecté
        if (sessionManager.isLoggedIn()) {
            navigateToMain()
            return
        }
        
        // Pré-remplir l'URL du serveur
        binding.etServerUrl.setText(sessionManager.getServerUrl())
        
        binding.btnLogin.setOnClickListener {
            performLogin()
        }
    }
    
    private fun performLogin() {
        val username = binding.etUsername.text.toString().trim()
        val password = binding.etPassword.text.toString().trim()
        val serverUrl = binding.etServerUrl.text.toString().trim()
        
        if (username.isEmpty() || password.isEmpty()) {
            showError("Veuillez saisir nom d'utilisateur et mot de passe")
            return
        }
        
        if (serverUrl.isEmpty()) {
            showError("Veuillez saisir l'URL du serveur")
            return
        }
        
        // Valider et formater l'URL
        val formattedUrl = formatServerUrl(serverUrl)
        if (formattedUrl == null) {
            showError("URL du serveur invalide")
            return
        }
        
        showLoading(true)
        
        lifecycleScope.launch {
            try {
                // Sauvegarder l'URL du serveur
                sessionManager.saveServerUrl(formattedUrl)
                
                // Créer un nouveau service API avec la nouvelle URL
                val apiService = ApiClient.updateBaseUrl(formattedUrl)
                
                // Effectuer la connexion
                val response = apiService.login(username, password)
                
                if (response.isSuccessful) {
                    // Tester immédiatement la validité de la session
                    val testResponse = apiService.getTasks()
                    if (testResponse.isSuccessful) {
                        // Connexion vraiment réussie, on réinitialise la conversation
                        try {
                            apiService.reset() // Appel à /reset pour vider l'historique
                        } catch (e: Exception) {
                            // Ne pas bloquer la connexion si le reset échoue.
                            // L'erreur pourrait être logguée ici si nécessaire.
                        }

                        sessionManager.saveLoginSession(username)
                        navigateToMain()
                    } else {
                        // Session invalide malgré le login réussi
                        showError("Échec de l'authentification")
                    }
                } else {
                    when (response.code()) {
                        401, 403 -> showError("Identifiants incorrects")
                        404 -> showError("Serveur non trouvé")
                        else -> showError("Erreur de connexion: ${response.code()}")
                    }
                }
                
            } catch (e: IOException) {
                showError("Erreur de réseau: vérifiez l'URL du serveur")
            } catch (e: HttpException) {
                showError("Erreur HTTP: ${e.code()}")
            } catch (e: Exception) {
                showError("Erreur: ${e.message}")
            } finally {
                showLoading(false)
            }
        }
    }
    
    private fun formatServerUrl(url: String): String? {
        var formattedUrl = url.trim()
        
        // Ajouter http:// si aucun protocole n'est spécifié
        if (!formattedUrl.startsWith("http://") && !formattedUrl.startsWith("https://")) {
            formattedUrl = "http://$formattedUrl"
        }
        
        // Ajouter / à la fin si nécessaire
        if (!formattedUrl.endsWith("/")) {
            formattedUrl += "/"
        }
        
        return try {
            java.net.URL(formattedUrl) // Valider l'URL
            formattedUrl
        } catch (e: Exception) {
            null
        }
    }
    
    private fun showLoading(show: Boolean) {
        binding.progressBar.visibility = if (show) View.VISIBLE else View.GONE
        binding.btnLogin.isEnabled = !show
        binding.etUsername.isEnabled = !show
        binding.etPassword.isEnabled = !show
        binding.etServerUrl.isEnabled = !show
    }
    
    private fun showError(message: String) {
        binding.tvError.text = message
        binding.tvError.visibility = View.VISIBLE
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
    }
    
    private fun navigateToMain() {
        val intent = Intent(this, MainActivity::class.java)
        intent.flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        startActivity(intent)
        finish()
    }
}