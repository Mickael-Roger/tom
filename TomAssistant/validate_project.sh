#!/bin/bash

echo "🔍 Validation du projet Tom Assistant Android"
echo "=============================================="

# Fonction pour vérifier l'existence d'un fichier
check_file() {
    if [ -f "$1" ]; then
        echo "✅ $1"
    else
        echo "❌ $1 - MANQUANT"
        return 1
    fi
}

# Fonction pour vérifier l'existence d'un dossier
check_dir() {
    if [ -d "$1" ]; then
        echo "✅ $1/"
    else
        echo "❌ $1/ - MANQUANT"
        return 1
    fi
}

echo
echo "📁 Structure du projet:"
check_dir "app"
check_dir "app/src"
check_dir "app/src/main"
check_dir "app/src/main/java"
check_dir "app/src/main/java/com"
check_dir "app/src/main/java/com/tom"
check_dir "app/src/main/java/com/tom/assistant"

echo
echo "📄 Fichiers de configuration:"
check_file "build.gradle.kts"
check_file "settings.gradle.kts"
check_file "gradle.properties"
check_file "app/build.gradle.kts"
check_file "app/proguard-rules.pro"

echo
echo "📱 Fichiers Android:"
check_file "app/src/main/AndroidManifest.xml"
check_file "gradlew"
check_file "gradle/wrapper/gradle-wrapper.properties"
check_file "gradle/wrapper/gradle-wrapper.jar"

echo
echo "🔧 Code source - Models:"
check_file "app/src/main/java/com/tom/assistant/models/LoginRequest.kt"
check_file "app/src/main/java/com/tom/assistant/models/ProcessRequest.kt"
check_file "app/src/main/java/com/tom/assistant/models/ProcessResponse.kt"
check_file "app/src/main/java/com/tom/assistant/models/ChatMessage.kt"

echo
echo "🌐 Code source - Network:"
check_file "app/src/main/java/com/tom/assistant/network/TomApiService.kt"
check_file "app/src/main/java/com/tom/assistant/network/ApiClient.kt"

echo
echo "🎨 Code source - UI:"
check_file "app/src/main/java/com/tom/assistant/ui/auth/LoginActivity.kt"
check_file "app/src/main/java/com/tom/assistant/ui/chat/ChatAdapter.kt"
check_file "app/src/main/java/com/tom/assistant/ui/tasks/TasksAdapter.kt"

echo
echo "🔧 Code source - Utils:"
check_file "app/src/main/java/com/tom/assistant/utils/SessionManager.kt"
check_file "app/src/main/java/com/tom/assistant/utils/AudioManager.kt"

echo
echo "📱 Activité principale:"
check_file "app/src/main/java/com/tom/assistant/MainActivity.kt"

echo
echo "🎨 Resources - Layouts:"
check_file "app/src/main/res/layout/activity_login.xml"
check_file "app/src/main/res/layout/activity_main.xml"
check_file "app/src/main/res/layout/item_chat_message.xml"
check_file "app/src/main/res/layout/item_task.xml"

echo
echo "🎨 Resources - Drawables:"
check_file "app/src/main/res/drawable/login_container_background.xml"
check_file "app/src/main/res/drawable/user_message_background.xml"
check_file "app/src/main/res/drawable/bot_message_background.xml"
check_file "app/src/main/res/drawable/ic_send.xml"
check_file "app/src/main/res/drawable/ic_mic.xml"

echo
echo "🎨 Resources - Values:"
check_file "app/src/main/res/values/colors.xml"
check_file "app/src/main/res/values/strings.xml"
check_file "app/src/main/res/values/themes.xml"

echo
echo "📊 Statistiques du projet:"
echo "- Fichiers Kotlin: $(find app/src/main/java -name "*.kt" | wc -l)"
echo "- Layouts XML: $(find app/src/main/res/layout -name "*.xml" | wc -l)"
echo "- Drawables XML: $(find app/src/main/res/drawable -name "*.xml" | wc -l)"

echo
echo "🔍 Vérification de la configuration Tailscale:"
if grep -q "server.taila2494.ts.net:8444" app/src/main/java/com/tom/assistant/network/ApiClient.kt; then
    echo "✅ URL Tailscale configurée dans ApiClient.kt"
else
    echo "❌ URL Tailscale non trouvée dans ApiClient.kt"
fi

if grep -q "server.taila2494.ts.net:8444" app/src/main/res/layout/activity_login.xml; then
    echo "✅ URL Tailscale configurée dans le layout de login"
else
    echo "❌ URL Tailscale non trouvée dans le layout de login"
fi

echo
echo "📱 Le projet est prêt pour Android Studio !"
echo "Pour compiler:"
echo "1. Ouvrir Android Studio"
echo "2. File → Open → Sélectionner ce dossier"
echo "3. Laisser Gradle se synchroniser"
echo "4. Build → Build Bundle(s) / APK(s) → Build APK(s)"