package com.example.tomapp;

import android.Manifest;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.webkit.GeolocationPermissions;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
import android.webkit.WebChromeClient;
import android.webkit.WebView;
import android.webkit.WebSettings;
import android.webkit.WebViewClient;

import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

import android.speech.tts.TextToSpeech;
import java.util.Locale;
import android.speech.tts.UtteranceProgressListener;

public class MainActivity extends AppCompatActivity {

    private TextToSpeech tts;
    private boolean isSpeaking = false;
    private WebView webView;

    private static final int PERMISSION_REQUEST_CODE = 1;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        setContentView(R.layout.activity_main);

        // Initialisation de TextToSpeech
        tts = new TextToSpeech(this, status -> {
            if (status == TextToSpeech.SUCCESS) {
                tts.setLanguage(Locale.ENGLISH); // Langue par défaut
            }
        });


        checkAndRequestPermissions();

        webView = findViewById(R.id.webView);
        WebSettings webSettings = webView.getSettings();

        // Enable JavaScript and other settings
        webSettings.setJavaScriptEnabled(true);
        webSettings.setDomStorageEnabled(true);
        webSettings.setAllowFileAccess(true);
        webSettings.setMediaPlaybackRequiresUserGesture(false);
        webSettings.setGeolocationEnabled(true);
        webSettings.setCacheMode(WebSettings.LOAD_CACHE_ELSE_NETWORK);
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(PermissionRequest request) {
                // Automatically grant microphone permission for the WebView
                request.grant(request.getResources());
            }
            @Override
            public void onGeolocationPermissionsShowPrompt(String origin, GeolocationPermissions.Callback callback) {
                callback.invoke(origin, true, false); // Toujours autoriser l'accès à la géolocalisation
            }
        });

        // Load your PWA URL or local HTML
        webView.setWebViewClient(new WebViewClient());
        webView.addJavascriptInterface(new TTSInterface(), "AndroidTTS");
        webView.loadUrl("https://server.taila2494.ts.net:8444");
    }

    @Override
    protected void onDestroy() {
        if (tts != null) {
            tts.stop();
            tts.shutdown();
        }
        super.onDestroy();
    }

    // Interface JavaScript pour exposer TTS aux scripts
    public class TTSInterface {

        @JavascriptInterface
        public void speak(String text, String language) {
            if (isSpeaking) {
                tts.stop(); // Arrêter le TTS en cours
                isSpeaking = false;
            }

            // Configuration de la langue
            Locale locale = language.equals("fr-FR") ? Locale.FRENCH : Locale.ENGLISH;
            int result = tts.setLanguage(locale);
            if (result == TextToSpeech.LANG_MISSING_DATA || result == TextToSpeech.LANG_NOT_SUPPORTED) {
                runOnUiThread(() -> {
                    webView.evaluateJavascript(
                            "console.error('Langue non prise en charge : " + language + "');", null);
                });
                return;
            }

            // Lecture du texte
            tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, null);
            isSpeaking = true;

            // Événement simulé pour indiquer la fin
            tts.setOnUtteranceProgressListener(new UtteranceProgressListener() {
                @Override
                public void onStart(String utteranceId) {
                    // Début de la lecture
                }

                @Override
                public void onDone(String utteranceId) {
                    isSpeaking = false;
                }

                @Override
                public void onError(String utteranceId) {
                    isSpeaking = false;
                }
            });
        }
    }

    private void checkAndRequestPermissions() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED ||
                ContextCompat.checkSelfPermission(this, Manifest.permission.MODIFY_AUDIO_SETTINGS) != PackageManager.PERMISSION_GRANTED ||
                ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED ||
                ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_COARSE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(
                    this,
                    new String[]{
                            Manifest.permission.RECORD_AUDIO,
                            Manifest.permission.MODIFY_AUDIO_SETTINGS,
                            Manifest.permission.ACCESS_FINE_LOCATION,
                            Manifest.permission.ACCESS_COARSE_LOCATION
                    },
                    PERMISSION_REQUEST_CODE
            );
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, @NonNull String[] permissions, @NonNull int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);

        if (requestCode == PERMISSION_REQUEST_CODE) {
            if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                // Permissions accordées
                System.out.println("Permissions accordées");
            } else {
                // Permissions refusées
                System.err.println("Permissions refusées. Le TTS ou la reconnaissance vocale pourraient ne pas fonctionner.");
            }
        }
    }
}

