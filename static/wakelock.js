let wakeLock = null;

async function requestWakeLock() {
    try {
        wakeLock = await navigator.wakeLock.request('screen');
        wakeLock.addEventListener('release', () => {
            console.log('Wake Lock a été libéré');
        });
    } catch (err) {
        console.error('Erreur lors de la demande de Wake Lock', err);
    }
}

// Appeler la fonction lorsque l'application est lancée ou active
requestWakeLock();

document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') {
        if (wakeLock !== null) {
            wakeLock.release();
            wakeLock = null;
        }
    } else {
        requestWakeLock();
    }
});

