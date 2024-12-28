importScripts('https://www.gstatic.com/firebasejs/9.22.1/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/9.22.1/firebase-messaging-compat.js');


//let firebaseConfig = {};
//
//fetch('/notificationconfig')
//.then(response => {
//    if (!response.ok) {
//        throw new Error("HTTP error " + response.status + " fetching notification config"); // Handle HTTP errors for config fetch
//    }
//    return response.json();
//})
//.then(data => {
//    firebaseConfig = data.firebaseConfig;

    firebaseConfig = {};

    firebase.initializeApp(firebaseConfig);
    
    // Get the messaging instance
    const messaging = firebase.messaging();

    //messaging.onMessage(function(payload) {
    //  // Customize notification here
    //  const notificationTitle = payload.data.title;
    //  const notificationOptions = {
    //    body: payload.data.body,
    //    icon: '/static/tom-192x192.png'
    //  };
    //
    //  return self.registration.showNotification(notificationTitle,
    //    notificationOptions);
    //});
   
    messaging.onBackgroundMessage(function(payload) {
      // Customize notification here
      const notificationTitle = payload.data.title;
      const notificationOptions = {
        body: payload.data.body,
        icon: '/static/tom-192x192.png'
      };
    
      return self.registration.showNotification(notificationTitle, notificationOptions);
    });


//})
//.catch(error => {
//    console.error("Error:", error.message); // More generic error message
//});



