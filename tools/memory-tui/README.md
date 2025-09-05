# Memory TUI

Interface graphique en terminal pour gérer les mémoires de Tom via l'API REST.

## Installation

```bash
cd tools/memory-tui
go mod tidy
go build -o memory-tui main.go
```

## Utilisation

L'URL de l'API REST est maintenant **obligatoire** en argument :

```bash
# Connexion à un serveur local
./memory-tui http://localhost:8080

# Connexion à un serveur distant
./memory-tui http://your-server:8080

# Ou via variable d'environnement
export MEMORY_API_URL=http://your-server:8080
./memory-tui http://fallback-url:8080
```

**Note**: L'URL doit inclure le protocole (http:// ou https://) et le port.

## Fonctionnalités

### Vue Liste (par défaut)
- **↑/↓** : Naviguer dans la liste
- **Enter** : Voir les détails d'une mémoire
- **a** : Ajouter une nouvelle mémoire
- **s** : Rechercher dans les mémoires
- **r** : Actualiser la liste
- **d** : Supprimer la mémoire sélectionnée
- **q** : Quitter l'application

### Vue Détails
- **Esc/q** : Retour à la liste

### Vue Ajout
- **Ctrl+S** : Sauvegarder la mémoire
- **Esc** : Annuler et retourner à la liste

### Vue Recherche
- **Enter** : Lancer la recherche
- **Esc** : Annuler et retourner à la liste

## API REST utilisée

L'application communique avec l'API REST du serveur memory :

- `GET /memories` - Liste toutes les mémoires
- `GET /memory/{id}` - Récupère une mémoire spécifique
- `POST /add` - Ajoute une nouvelle mémoire
- `POST /search` - Recherche dans les mémoires
- `DELETE /delete/{id}` - Supprime une mémoire

## Dépendances

- [Bubble Tea](https://github.com/charmbracelet/bubbletea) - Framework TUI
- [Bubbles](https://github.com/charmbracelet/bubbles) - Composants TUI
- [Lipgloss](https://github.com/charmbracelet/lipgloss) - Stylisation