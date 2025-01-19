package com.example.tomapp;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.view.KeyEvent;
import android.util.Log;

public class MediaButtonReceiver extends BroadcastReceiver {
    private static final String TAG = "MediaButtonReceiver";

    @Override
    public void onReceive(Context context, Intent intent) {
        if (Intent.ACTION_MEDIA_BUTTON.equals(intent.getAction())) {
            KeyEvent keyEvent = intent.getParcelableExtra(Intent.EXTRA_KEY_EVENT);
            if (keyEvent != null && keyEvent.getAction() == KeyEvent.ACTION_DOWN) {
                Log.d("MediaButtonReceiver", "Received media button: " + keyEvent.getKeyCode());
                if (keyEvent.getKeyCode() == KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE) {
                    Log.d("MediaButtonReceiver", "Play/Pause detected, launching activity");
                    Intent startIntent = new Intent(context, MainActivity.class);
                    startIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                    startIntent.putExtra("trigger_speak", true);
                    context.startActivity(startIntent);
                }
            }
        }
    }
}
