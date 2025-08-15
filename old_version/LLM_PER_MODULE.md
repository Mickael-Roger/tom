# Configuration LLM par Module

Cette fonctionnalité permet à chaque module d'utiliser un LLM spécifique différent du LLM par défaut configuré globalement.

## Utilisation

**IMPORTANT** : La configuration LLM se fait **toujours** dans la section `services` au niveau global, que le module soit global ou personnel.

### Configuration unifiée

Dans `config.yml`, section `services` globale, ajoutez le paramètre `llm` :

```yaml
services:
  # Module global avec LLM personnalisé
  weather:
    llm: mistral  # Ce module utilisera Mistral
    
  # Module global avec token ET LLM personnalisé  
  idfm:
    token: XXXXXXXXXXXXXXXXXXXXXXXX
    llm: deepseek  # Ce module utilisera DeepSeek
    
  # Module personnel avec LLM personnalisé
  calendar:
    llm: gemini   # Même si c'est un module personnel, la config LLM est ici
    
  todo:
    llm: anthropic  # Configuration LLM centralisée

users:
  - username: user1
    password: password1
    services:
      # Activation et configuration personnelle des modules
      calendar:
        enable: true
        url: https://caldav-server.com/
        user: caldav_user  
        password: caldav_pass
        # PAS de 'llm' ici - c'est dans services global
        
      todo:
        enable: true
        # PAS de 'llm' ici - c'est dans services global
```

## Exemples concrets

### Optimisation par tâche

```yaml
services:
  # Module météo - tâche simple, utilise un LLM rapide et économique
  weather:
    llm: gemini
    
  # Module d'analyse de données complexes - utilise un LLM plus puissant
  analytics:
    llm: deepseek
    
  # Module créatif - utilise un LLM créatif
  content_generator:
    llm: anthropic

users:
  - username: developer
    services:
      # Module de code - utilise un LLM spécialisé en code
      code_assistant:
        enable: true
        llm: deepseek
        
      # Module de traduction - utilise un LLM multilingue
      translator:
        enable: true
        llm: gemini
```

## Fonctionnement

1. **Fallback automatique** : Si le LLM spécifié n'est pas disponible, le module utilisera le LLM par défaut
2. **Logs informatifs** : Les changements de LLM sont enregistrés dans les logs
3. **Pas de modification de code** : Les modules existants continuent de fonctionner sans modification
4. **Configuration flexible** : Peut être définie globalement ou par utilisateur

## Validation

Le système vérifie automatiquement :
- Que le LLM spécifié existe dans la configuration `global.llms`
- Que le LLM est correctement configuré avec une clé API valide
- En cas d'erreur, il utilise le LLM par défaut et log un avertissement

## Cas d'usage recommandés

- **Modules simples** (météo, heure) → LLM rapide (Gemini Flash, GPT-4o-mini)
- **Modules analytiques** (finances, statistiques) → LLM de raisonnement (DeepSeek Reasoner)
- **Modules créatifs** (rédaction, brainstorming) → LLM créatif (Claude, GPT-4o)
- **Modules de code** (développement, debugging) → LLM spécialisé code (DeepSeek)
- **Modules multilingues** → LLM avec bon support multilingue (Gemini, GPT-4o)