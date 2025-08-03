# Documentation des Modules d'Extension Tom

Cette documentation présente tous les modules d'extension disponibles pour l'assistant Tom, organisés par type et domaine d'application.

## Table des Matières

- [Vue d'ensemble](#vue-densemble)
- [Configuration](#configuration)
- [Modules Globaux](#modules-globaux)
- [Modules Personnels](#modules-personnels)
- [Guide de Développement](#guide-de-développement)

## Vue d'ensemble

L'assistant Tom propose une architecture modulaire avec deux types de modules :

- **Modules Globaux** : Partagés entre tous les utilisateurs, configurés au niveau serveur
- **Modules Personnels** : Configuration et données par utilisateur

### Complexité des Modules

- **Niveau 0** : Modules simples avec fonctionnalités de base
- **Niveau 1** : Modules avancés avec cache, traitements asynchrones ou logique métier complexe

## Configuration

### Structure de Configuration

```yaml
# Configuration globale (config.yml)
services:
  module_name:
    parameter1: value1
    parameter2: value2

# Configuration utilisateur
users:
  - username: user1
    services:
      module_name:
        enable: true
        parameter1: user_value1
```

### Types de Paramètres

- **string** : Chaîne de caractères
- **integer** : Nombre entier
- **boolean** : true/false
- **array** : Liste de valeurs
- **object** : Structure complexe

---

## Modules Globaux

Les modules globaux sont partagés entre tous les utilisateurs. Ils sont configurés au niveau serveur et activés individuellement par chaque utilisateur.

### 🍽️ cafetaria - Gestion Cantine Scolaire

**Complexité :** 0 | **Type :** Global

Gestion complète de la cantine scolaire : réservations, annulations, consultation du solde.

#### Configuration

```yaml
services:
  cafetaria:
    username: "nom_utilisateur_cantine"  # requis
    password: "mot_de_passe_cantine"     # requis
```

#### Fonctions Disponibles

- `get_cafetaria_credit` : Consultation du crédit cantine restant
- `list_cafetaria_reservations` : Liste des réservations en cours
- `make_a_cafetaria_reservation` : Réserver un repas
- `cancel_a_cafetaria_reservation` : Annuler une réservation

#### Activation Utilisateur

```yaml
users:
  - username: user1
    services:
      cafeteria:
        enable: true
```

---

### 📞 contacts - Carnet d'Adresses

**Complexité :** 0 | **Type :** Global

Carnet d'adresses partagé avec gestion flexible des contacts.

#### Configuration

Aucune configuration requise.

#### Fonctions Disponibles

- `add_contact` : Ajouter un nouveau contact (structure flexible)
- `get_contacts` : Obtenir la liste complète des contacts
- `delete_contact` : Supprimer un contact par nom

#### Activation Utilisateur

```yaml
users:
  - username: user1
    services:
      contacts:
        enable: true
```

---

### 🤖 deebot - Robot Aspirateur

**Complexité :** 0 | **Type :** Global

Contrôle et surveillance d'un robot aspirateur Deebot (aspiration, serpillère, navigation).

#### Configuration

```yaml
services:
  deebot:
    username: "email@example.com"  # requis - Email du compte Deebot
    password: "mot_de_passe"       # requis - Mot de passe du compte
    country: "FR"                  # optionnel - Code pays (défaut: FR)
```

#### Fonctions Disponibles

- `get_vacuum_robot_status` : État complet (batterie, position, erreurs)
- `stop_vacuum_robot` : Arrêter le nettoyage en cours
- `go_to_base_station` : Retour à la base de charge
- `start_vacuum_robot_cleaning` : Démarrer nettoyage (type configurable)
- `get_vacuum_robot_rooms` : Lister les pièces disponibles

#### Activation Utilisateur

```yaml
users:
  - username: user1
    services:
      deebot:
        enable: true
```

---

### 🚇 idfm - Transports Île-de-France

**Complexité :** 1 | **Type :** Global

Informations en temps réel sur les transports publics franciliens (RATP, SNCF Transilien).

#### Configuration

```yaml
services:
  idfm:
    token: "votre_token_api_idfm"  # requis - Token API IDFM
```

#### Fonctions Disponibles

- `search_station` : Rechercher une station par nom
- `search_place_gps` : Obtenir coordonnées GPS d'un lieu
- `plan_a_journey` : Calculer un itinéraire entre deux points
- `select_a_route` : Sélectionner un itinéraire proposé
- `retreived_current_selected_route` : Récupérer l'itinéraire en cours

#### Activation Utilisateur

```yaml
users:
  - username: user1
    services:
      idfm:
        enable: true
```

---

### 📐 kwyk - Exercices Mathématiques

**Complexité :** 0 | **Type :** Global

Suivi des exercices et statistiques sur la plateforme éducative Kwyk.

#### Configuration

```yaml
services:
  kwyk:
    username: "nom_utilisateur_kwyk"  # requis
    password: "mot_de_passe_kwyk"     # requis
    id: "id_utilisateur_kwyk"         # requis - ID numérique
```

#### Fonctions Disponibles

- `kwyk_get` : Obtenir statistiques d'exercices sur une période donnée

#### Activation Utilisateur

```yaml
users:
  - username: user1
    services:
      kwyk:
        enable: true
```

---

### 🎮 switchparentalcontrol - Contrôle Parental Nintendo

**Complexité :** 1 | **Type :** Global

Gestion du contrôle parental pour les consoles Nintendo Switch (temps d'utilisation, restrictions).

#### Configuration

```yaml
services:
  switchparentalcontrol:
    nintendo_session_token: "eyJhbGciOiJSUzI1NiIs..."  # requis - Token de session Nintendo
```

> **Note** : Utilisez le script `tools/nintendo_switch_parental_control_auth_token.py` pour obtenir votre token.

#### Fonctions Disponibles

- `get_switch_daily_usage` : Temps d'utilisation quotidien par console
- `extend_switch_playtime` : Étendre le temps de jeu (1-480 minutes)
- `reduce_switch_playtime` : Réduire le temps de jeu (1-480 minutes)
- `list_switch_devices` : Lister toutes les consoles Nintendo Switch

#### Gestion des Limites

- **Limite = 0** : Console bloquée (aucun jeu autorisé)
- **Limite = null** : Temps de jeu illimité
- **Limite > 0** : Temps limité en minutes

#### Activation Utilisateur

```yaml
users:
  - username: user1
    services:
      switchparentalcontrol:
        enable: true
```

---

### 🌤️ weather - Météo

**Complexité :** 0 | **Type :** Global

Prévisions météorologiques détaillées utilisant l'API Open-Meteo (gratuite).

#### Configuration

Aucune configuration requise (utilise l'API Open-Meteo gratuite).

#### Fonctions Disponibles

- `weather_get_by_gps_position` : Météo par coordonnées GPS avec période
- `get_gps_position_by_city_name` : Obtenir coordonnées d'une ville

#### Cache Automatique

Le module met en cache les coordonnées GPS des villes pour optimiser les performances.

#### Activation Utilisateur

```yaml
users:
  - username: user1
    services:
      weather:
        enable: true
```

---

## Modules Personnels

Les modules personnels stockent leurs données et configuration par utilisateur. Chaque utilisateur a sa propre instance isolée.

### 🧠 anki - Cartes Mémoire

**Complexité :** 1 | **Type :** Personnel

Interface avec l'application Anki pour la gestion des cartes de révision.

#### Configuration

```yaml
users:
  - username: user1
    services:
      anki:
        enable: true
        url: "http://localhost:8765"  # requis - URL AnkiConnect
        profile: "nom_profil"         # requis - Nom du profil Anki
```

#### Prérequis

- Anki installé avec le plugin AnkiConnect
- AnkiConnect configuré et actif

#### Fonctions Disponibles

- `anki_list_decks` : Lister tous les paquets de cartes
- `anki_list_all_cards` : Lister toutes les cartes d'un paquet
- `anki_add_card` : Ajouter une nouvelle carte à un paquet

---

### 📅 calendar - Calendrier CalDAV

**Complexité :** 0 | **Type :** Personnel

Gestion complète du calendrier personnel via le protocole CalDAV.

#### Configuration

```yaml
users:
  - username: user1
    services:
      calendar:
        enable: true
        url: "https://caldav.exemple.com/"  # requis - URL serveur CalDAV
        user: "utilisateur_caldav"          # requis - Nom d'utilisateur
        password: "mot_de_passe_caldav"     # requis - Mot de passe
        calendar_name: "personnel"          # requis - Nom du calendrier
```

#### Serveurs CalDAV Compatibles

- Nextcloud, ownCloud
- Google Calendar, iCloud
- Zimbra, SOGo
- Serveurs CalDAV standards

#### Fonctions Disponibles

- `calendar_search_event` : Rechercher des événements par période
- `calendar_add_event` : Ajouter un nouvel événement
- `calendar_delete_event` : Supprimer un événement par UID
- `calendar_update_event` : Modifier un événement existant

---

### 🏃 sport_coach - Coach Sportif

**Complexité :** 1 | **Type :** Personnel

Coach sportif personnel avec historique des activités et recommandations.

#### Configuration

```yaml
users:
  - username: user1
    services:
      sport_coach:
        enable: true
        cache_db: "/chemin/vers/sport.sqlite"  # requis - Base de données SQLite
```

#### Fonctions Disponibles

- `get_sport_history` : Récupérer l'historique sportif sur une période
- `record_sport_history` : Enregistrer une nouvelle activité sportive

#### Base de Données

Le module crée automatiquement une base SQLite pour stocker l'historique des activités.

---

### 🛒 groceries - Liste de Courses

**Complexité :** 0 | **Type :** Personnel

Gestion de liste de courses synchronisée via CalDAV (compatible avec la plupart des apps de liste).

#### Configuration

```yaml
users:
  - username: user1
    services:
      groceries:
        enable: true
        url: "https://caldav.exemple.com/"  # requis - URL serveur CalDAV
        user: "utilisateur"                 # optionnel - Nom d'utilisateur
        password: "mot_de_passe"            # requis - Mot de passe
        list: "courses"                     # requis - Nom de la liste
```

#### Fonctions Disponibles

- `grocery_list_content` : Lister tous les produits avec leur statut
- `grocery_list_add` : Ajouter un produit à la liste
- `grocery_list_remove` : Supprimer un produit de la liste

---

### 📰 news - Actualités

**Complexité :** 1 | **Type :** Personnel

Agrégateur d'actualités avec support RSS et web scraping intelligent.

#### Configuration

```yaml
users:
  - username: user1
    services:
      news:
        enable: true
        url: "https://rss.exemple.com/"     # requis - URL serveur RSS
        user: "utilisateur_rss"             # requis - Nom d'utilisateur
        password: "mot_de_passe_rss"        # requis - Mot de passe
        cache_db: "/chemin/vers/news.sqlite" # requis - Base de données SQLite
```

#### Fonctions Disponibles

- `get_all_news` : Lister toutes les actualités non lues
- `get_news_summary` : Obtenir le résumé d'un article (web scraping)
- `mark_news_as_read` : Marquer un article comme lu
- `mark_news_to_read` : Marquer un article à lire plus tard

#### Fonctionnalités Avancées

- Cache intelligent des articles
- Web scraping automatique pour les résumés
- Gestion des états de lecture

---

### 🎓 pronote - Vie Scolaire

**Complexité :** 1 | **Type :** Personnel

Interface complète avec Pronote pour le suivi scolaire (notes, devoirs, emploi du temps).

#### Configuration

```yaml
users:
  - username: user1
    services:
      pronote:
        enable: true
        children:
          - name: "enfant1"
            token: "/chemin/vers/token1.json"
            cache: "/chemin/vers/cache1.sqlite"
          - name: "enfant2" 
            token: "/chemin/vers/token2.json"
            cache: "/chemin/vers/cache2.sqlite"
```

#### Génération des Tokens

Utilisez la bibliothèque `pronotepy` pour générer les fichiers de tokens d'authentification.

#### Fonctions Disponibles

- `list_grade_averages` : Moyennes par matière et générale
- `list_grades` : Toutes les notes avec détails
- `list_homeworks` : Devoirs à faire avec dates
- `list_school_absences` : Absences scolaires
- `list_school_delays` : Retards scolaires
- `list_school_evaluations` : Évaluations et compétences
- `list_school_punishments` : Sanctions disciplinaires
- `list_school_observations` : Observations des professeurs
- `list_school_information_communication` : Messages de l'établissement
- `get_school_information_communication_message` : Contenu d'un message
- `list_school_teachers` : Liste des professeurs
- `get_school_calendar` : Emploi du temps
- `pronote_mark_as_seen` : Marquer un élément comme vu

---

### ⚙️ techcapabilities - Capacités Techniques

**Complexité :** 1 | **Type :** Personnel

Exécution de tâches techniques complexes sur une machine virtuelle Debian distante via SSH.

#### Configuration

```yaml
users:
  - username: user1
    services:
      techcapabilities:
        enable: true
        tasks_dir: "/chemin/vers/taches/"     # requis - Répertoire des tâches
        host: "192.168.1.100"                # requis - IP/hostname de la VM
        username: "utilisateur_vm"           # requis - Nom d'utilisateur SSH
        ssh_key_path: "/chemin/vers/cle.pem" # requis - Clé privée SSH
```

#### Prérequis

- VM Debian avec accès SSH par clé
- Répertoire de tâches accessible en écriture
- Connexion réseau stable

#### Fonctions Disponibles

- `create_tech_task` : Créer une tâche technique asynchrone
- `list_tech_tasks` : Lister toutes les tâches avec statuts
- `get_task_details` : Détails complets d'une tâche
- `get_task_results` : Résultats finaux uniquement
- `cancel_task` : Annuler une tâche en cours

#### Sécurité

- Exécution isolée sur VM dédiée
- Authentification par clé SSH uniquement
- Logs détaillés de toutes les opérations

---

### ✅ todo - Liste de Tâches

**Complexité :** 0 | **Type :** Personnel

Gestion de listes de tâches via CalDAV, compatible avec la plupart des applications TODO.

#### Configuration

```yaml
users:
  - username: user1
    services:
      todo:
        enable: true
        url: "https://caldav.exemple.com/"  # requis - URL serveur CalDAV
        user: "utilisateur_caldav"          # requis - Nom d'utilisateur
        password: "mot_de_passe_caldav"     # requis - Mot de passe
        list: "taches"                      # requis - Nom de la liste TODO
```

#### Fonctions Disponibles

- `todo_list_all` : Lister toutes les tâches avec leur statut
- `todo_create_task` : Créer une nouvelle tâche
- `todo_close_task` : Marquer une tâche comme terminée

---

### 📺 youtube - Chaînes YouTube

**Complexité :** 1 | **Type :** Personnel

Suivi automatique des nouvelles vidéos de vos chaînes YouTube préférées.

#### Configuration

```yaml
users:
  - username: user1
    services:
      youtube:
        enable: true
        cache_db: "/chemin/vers/youtube.sqlite"  # requis - Base de données SQLite
```

#### Fonctions Disponibles

- `get_all_new_videos` : Lister toutes les nouvelles vidéos non vues
- `mark_video_as_seen` : Marquer une ou plusieurs vidéos comme vues

#### Fonctionnalités

- Détection automatique des nouvelles vidéos
- Cache intelligent pour éviter les doublons
- Support pour multiple chaînes

---

## Guide de Développement

### Structure d'un Module

```python
tom_config = {
    "module_name": "nom_unique",
    "class_name": "NomClasse",
    "description": "Description du module",
    "type": "global" | "personal",
    "complexity": 0 | 1,
    "configuration_parameters": {
        "param1": {
            "type": "string",
            "description": "Description du paramètre",
            "required": True
        }
    }
}

class NomClasse:
    def __init__(self, config, llm):
        # Initialisation
        self.tools = [...]      # Outils OpenAI Function Calling
        self.functions = {...}  # Mapping nom -> implémentation
        
    @property
    def systemContext(self):
        return "Contexte pour le LLM"
```

### Bonnes Pratiques

1. **Gestion d'erreurs** : Toujours capturer et loguer les erreurs
2. **Cache intelligent** : Utiliser SQLite pour la persistance
3. **Configuration flexible** : Paramètres optionnels avec valeurs par défaut
4. **Documentation** : Descriptions claires des fonctions et paramètres
5. **Sécurité** : Ne jamais loguer de mots de passe ou tokens
6. **Tests** : Créer des tests unitaires pour chaque module

### Ajout d'un Nouveau Module

1. Créer le fichier `modules/tomnouveau.py`
2. Implémenter la structure standard
3. Ajouter les tests dans `tests/test_tomnouveau.py`
4. Mettre à jour cette documentation
5. Tester avec la configuration de développement

---

*Cette documentation est maintenue à jour avec chaque version de Tom. Pour des questions spécifiques ou des demandes de nouveaux modules, consultez le fichier `dev.md`.*