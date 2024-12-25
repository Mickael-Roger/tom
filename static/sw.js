// Gestion des notifications locales
self.addEventListener('push', event => {
  const data = event.data.json();
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: data.icon || '/static/tom-96x96.png.png',
    })
  );
});

// Gestion de la synchronisation périodique
self.addEventListener('periodicsync', async event => {
  if (event.tag === 'sync-notifications') {
    event.waitUntil(syncNotifications());
  }
});

// Fonction pour synchroniser les notifications depuis le backend
async function syncNotifications() {
  try {
    const response = await fetch('/notifications');
    if (!response.ok) {
      throw new Error(`Erreur HTTP : ${response.status}`);
    }
    const notifications = await response.json();
    saveNotifications(notifications);
    planNotifications(notifications);
  } catch (error) {
    console.error('Erreur lors de la synchronisation des notifications :', error);
    // Si une erreur se produit, nous essayons de récupérer les notifications stockées
    const storedNotifications = localStorage.getItem('notifications');
    if (storedNotifications) {
      planNotifications(JSON.parse(storedNotifications));
    } else {
      console.warn('Aucune notification disponible en mode hors ligne.');
    }
  }
}

// Sauvegarder les notifications dans localStorage
function saveNotifications(notifications) {
  localStorage.setItem('notifications', JSON.stringify(notifications));
}

// Planification des notifications
const pendingNotifications = new Map();

function planNotifications(notifications) {
  const currentKeys = new Set(notifications.map(n => n.datetime));
  // Supprimer les notifications annulées
  for (const [datetime] of pendingNotifications) {
    if (!currentKeys.has(datetime)) {
      clearTimeout(pendingNotifications.get(datetime));
      pendingNotifications.delete(datetime);
    }
  }

  // Planifier les nouvelles notifications
  notifications.forEach(({ datetime, message }) => {
    if (!pendingNotifications.has(datetime)) {
      scheduleNotification(datetime, message);
    }
  });
}

function scheduleNotification(datetime, message) {
  const delay = new Date(datetime).getTime() - Date.now();
  if (delay <= 0) {
    console.warn(`Notification ignorée, datetime est passé : ${datetime}`);
    return;
  }

  const timeoutId = setTimeout(() => {
    showNotification(message);
    pendingNotifications.delete(datetime); // Supprimer après affichage
  }, delay);

  pendingNotifications.set(datetime, timeoutId);
}

function showNotification(message) {
  self.registration.showNotification('Nouvelle Notification', {
    body: message,
    icon: '/static/tom-96x96.png', // Optionnel : icône par défaut
  });
}

