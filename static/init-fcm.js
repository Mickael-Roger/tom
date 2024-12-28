let firebaseConfig = {};
let vapidKey = "";
let messaging;

function requestToken() {
    if (!messaging) {
        console.error("Messaging not initialized. Cannot request token.");
        return;
    }

    messaging.getToken({ vapidKey: vapidKey }).then((currentToken) => {
        if (currentToken) {
            console.log("FCM Token:", currentToken);
            fetch('/fcmtoken', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    token: currentToken,
                    platform: getPlatform()
                })
            })
            .then(response => {
                if (!response.ok) {
                    return response.json().then(err => { throw new Error(err.error || "HTTP error " + response.status); });
                }
                return response.ok;
            })
            .then(data => console.log("Token sent:", data.message))
            .catch(error => console.error("Error sending token:", error.message));
        } else {
            console.log('No registration token available. Request permission to generate one.');
            Notification.requestPermission().then((permission) => {
                if (permission === 'granted') {
                    console.log('Notification permission granted.');
                    requestToken();
                } else {
                    console.log('Unable to get permission to notify.');
                }
            });
        }
    }).catch((err) => {
        console.error('An error occurred while retrieving token: ', err);
    });
}

function getPlatform() {
    if (navigator.userAgent.match(/Android/i)) {
        return "android";
    } else if (navigator.userAgent.match(/iPhone|iPad|iPod/i)) {
        return "ios";
    } else if (navigator.userAgent.match(/Linux/i)) {
        return "linux";
    } else if (navigator.userAgent.match(/Macintosh|Mac OS X/i)) {
      return "macos";
    } else if (navigator.userAgent.match(/Windows/i)) {
        return "windows"; 
    } else {
        return "other"; // Default if no match
    }
}

function registerServiceWorkerAndGetToken() {
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/firebase-messaging-sw.js')
        .then(registration => {
            console.log('Service Worker registered with scope:', registration.scope);
            return navigator.serviceWorker.ready;
        })
        .then(registration => {
            console.log('Service Worker is ready.');
            requestToken();
        })
        .catch(error => {
            console.error('Service Worker registration failed:', error);
        });
    } else {
        console.log('This browser doesn\'t support service workers.');
    }
}

fetch('/notificationconfig')
.then(response => {
    if (!response.ok) {
        throw new Error("HTTP error " + response.status + " fetching notification config"); // Handle HTTP errors for config fetch
    }
    return response.json();
})
.then(data => {
    firebaseConfig = data.firebaseConfig;
    vapidKey = data.vapidKey;

    firebase.initializeApp(firebaseConfig);
    messaging = firebase.messaging();

    registerServiceWorkerAndGetToken();

    messaging.onMessage((payload) => {
      alert(payload.data.body);
    //    console.log('Message received. ', payload);
    //    const notificationTitle = payload.data.title;
    //    const notificationOptions = {
    //        body: payload.data.body,
    //        icon: '/static/tom-192x192.png'
    //    };
    //    new Notification(notificationTitle, notificationOptions);
    });
})
.catch(error => {
    console.error("Error:", error.message); // More generic error message
});
