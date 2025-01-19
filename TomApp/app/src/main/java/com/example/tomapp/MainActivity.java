package com.example.tomapp;

import android.Manifest;
import android.content.Context;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.media.AudioManager;
import android.media.session.MediaSession;
import android.media.session.PlaybackState;
import android.os.Build;
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
import android.util.Log;
import android.content.Intent;
import android.view.KeyEvent;
import android.webkit.CookieManager;

public class MainActivity extends AppCompatActivity {

    private TextToSpeech tts;
    private boolean isSpeaking = false;
    private WebView webView;
    private MediaSession mediaSession;

    private static final int PERMISSION_REQUEST_CODE = 1;
    private static final String SPEAK_TRIGGER_EXTRA = "trigger_speak";

    private MediaButtonReceiver mediaButtonReceiver;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        // Initialize TextToSpeech
        tts = new TextToSpeech(this, status -> {
            if (status == TextToSpeech.SUCCESS) {
                tts.setLanguage(Locale.ENGLISH);
            }
        });

        checkAndRequestPermissions();

        webView = findViewById(R.id.webView);
        WebSettings webSettings = webView.getSettings();
        webSettings.setJavaScriptEnabled(true);
        webSettings.setDomStorageEnabled(true);
        webSettings.setAllowFileAccess(true);
        webSettings.setMediaPlaybackRequiresUserGesture(false);
        webSettings.setGeolocationEnabled(true);
        webSettings.setCacheMode(WebSettings.LOAD_CACHE_ELSE_NETWORK);

        // Enable cookie management
        CookieManager cookieManager = CookieManager.getInstance();
        cookieManager.setAcceptCookie(true);
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.LOLLIPOP) {
            cookieManager.setAcceptThirdPartyCookies(webView, true);
        }

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(PermissionRequest request) {
                request.grant(request.getResources());
            }
            @Override
            public void onGeolocationPermissionsShowPrompt(String origin, GeolocationPermissions.Callback callback) {
                callback.invoke(origin, true, false);
            }
        });

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                cookieManager.flush();
            }
        });

        webView.addJavascriptInterface(new TTSInterface(), "AndroidTTS");
        webView.loadUrl("https://server.taila2494.ts.net:8444/index");

        // Vérifier si l'intent a un trigger pour parler
        if (getIntent().getBooleanExtra(SPEAK_TRIGGER_EXTRA, false)) {
            webView.evaluateJavascript("document.getElementById('speak-button').click();", null);
        }

        setupMediaSession();

        // Enregistrer le BroadcastReceiver pour capturer les événements des boutons multimédias
        IntentFilter filter = new IntentFilter(Intent.ACTION_MEDIA_BUTTON);
        filter.setPriority(IntentFilter.SYSTEM_HIGH_PRIORITY); // Priorité maximale pour capter les événements
        //MediaButtonReceiver
        mediaButtonReceiver = new MediaButtonReceiver();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {  // Android 13+
            registerReceiver(mediaButtonReceiver, filter, Context.RECEIVER_EXPORTED);
        } else {
            registerReceiver(mediaButtonReceiver, filter);
        }


    }

    @Override
    protected void onStop() {
        super.onStop();
        if (mediaButtonReceiver != null) {
            unregisterReceiver(mediaButtonReceiver);
            mediaButtonReceiver = null;
            Log.d("MainActivity", "MediaButtonReceiver unregistered.");
        }
    }

    private void setupMediaSession() {
        mediaSession = new MediaSession(this, "MediaSessionTag");

        PlaybackState playbackState = new PlaybackState.Builder()
                .setActions(PlaybackState.ACTION_PLAY | PlaybackState.ACTION_PAUSE | PlaybackState.ACTION_PLAY_PAUSE)
                .setState(PlaybackState.STATE_PLAYING, 0, 1.0f)
                .build();
        mediaSession.setPlaybackState(playbackState);
        mediaSession.setActive(true);
        Log.d("MediaSession", "MediaSession active and handling events.");

        mediaSession.setCallback(new MediaSession.Callback() {
            @Override
            public boolean onMediaButtonEvent(Intent mediaButtonIntent) {
                KeyEvent event = mediaButtonIntent.getParcelableExtra(Intent.EXTRA_KEY_EVENT);
                if (event != null) {
                    Log.d("MediaSession", "Received media button event: " + event.toString());
                    if (event.getAction() == KeyEvent.ACTION_DOWN) {
                        int keyCode = event.getKeyCode();
                        Log.d("MediaSession", "Media button pressed: " + keyCode);

                        if (keyCode == KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE || keyCode == KeyEvent.KEYCODE_HEADSETHOOK) {
                            Log.d("MediaSession", "Play/Pause or Headset Hook pressed");
                            runOnUiThread(() -> webView.evaluateJavascript("document.getElementById('speak-button').click();", null));
                        }
                    }
                }
                return super.onMediaButtonEvent(mediaButtonIntent);
            }
        });





    }




    @Override
    protected void onDestroy() {
        if (tts != null) {
            tts.stop();
            tts.shutdown();
        }
        if (mediaSession != null) {
            mediaSession.release();
        }
        super.onDestroy();
    }

    public class TTSInterface {
        @JavascriptInterface
        public void speak(String text, String language) {
            if (isSpeaking) {
                tts.stop();
                isSpeaking = false;
            }

            Locale locale = language.equals("fr-FR") ? Locale.FRENCH : Locale.ENGLISH;
            int result = tts.setLanguage(locale);
            if (result == TextToSpeech.LANG_MISSING_DATA || result == TextToSpeech.LANG_NOT_SUPPORTED) {
                runOnUiThread(() -> webView.evaluateJavascript("console.error('Langue non prise en charge : " + language + "');", null));
                return;
            }

            tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "UniqueID");
            isSpeaking = true;
        }
    }

    private void checkAndRequestPermissions() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED ||
                ContextCompat.checkSelfPermission(this, Manifest.permission.MODIFY_AUDIO_SETTINGS) != PackageManager.PERMISSION_GRANTED ||
                ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED ||
                ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(
                    this,
                    new String[]{
                            Manifest.permission.RECORD_AUDIO,
                            Manifest.permission.MODIFY_AUDIO_SETTINGS,
                            Manifest.permission.ACCESS_FINE_LOCATION,
                            Manifest.permission.BLUETOOTH_CONNECT
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
                Log.d("Permissions", "All permissions granted");
            } else {
                Log.e("Permissions", "Some permissions were denied");
            }
        }
    }
}
