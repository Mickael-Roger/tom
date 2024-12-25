// Demander la permission de notification à l'utilisateur
async function requestNotificationPermission() {
  if ('Notification' in window && Notification.permission !== 'granted') {
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') {
      console.warn('Permission de notification refusée.');
    }
  }
}

// Enregistrer la synchronisation périodique
async function registerBackgroundSync() {
  if ('serviceWorker' in navigator && 'periodicSync' in navigator.serviceWorker) {
    try {
      const registration = await navigator.serviceWorker.ready;
      await registration.periodicSync.register('sync-notifications', {
        minInterval: 5 * 60 * 1000, // 5 minutes
      });
      console.log('Synchronisation périodique enregistrée avec succès.');
    } catch (error) {
      console.error('Erreur lors de l’enregistrement de la synchronisation périodique :', error);
    }
  } else {
    console.warn('L’API Periodic Background Sync n’est pas prise en charge. Fallback au polling.');
    startPollingNotifications(); // Utilisation du fallback si Periodic Sync n'est pas disponible
  }
}

// Fallback : Polling régulier
async function startPollingNotifications() {
  setInterval(async () => {
    await fetchNotifications();
  }, 5 * 60 * 1000); // Toutes les 5 minutes
}

// Fonction pour récupérer les notifications depuis le backend
async function fetchNotifications() {
  try {
    const response = await fetch('/notifications');
    if (!response.ok) {
      throw new Error(`Erreur HTTP : ${response.status}`);
    }
    const notifications = await response.json();
    navigator.serviceWorker.ready.then(swRegistration => {
      swRegistration.active.postMessage({ type: 'plan-notifications', notifications });
    });
  } catch (error) {
    console.error('Erreur lors de la récupération des notifications :', error);
    // Afficher une notification d'erreur locale
    showErrorNotification('Échec de la récupération des notifications.');
  }
}

// Afficher une notification d'erreur locale
function showErrorNotification(message) {
  if ('Notification' in window) {
    new Notification('Erreur', {
      body: message,
      icon: '/static/tom-96x96.png',
    });
  }
}

// Initialisation
async function init() {
  if ('serviceWorker' in navigator) {
    await navigator.serviceWorker.register('/static/sw.js');
    console.log('Service Worker enregistré.');
  }
  await requestNotificationPermission();
  await fetchNotifications(); // Appel immédiat au lancement
  await registerBackgroundSync(); // Tente d'utiliser Background Sync
}

// Démarrer l'application
init();

