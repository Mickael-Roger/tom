#!/bin/bash

# Créer des icônes PNG très simples en utilisant convert (ImageMagick) s'il est disponible
# Sinon, on utilise juste l'icône drawable XML

BASE_DIR="/home/mickael/Documents/Dev/tom/TomAssistant/app/src/main/res"

# Vérifier si ImageMagick est disponible
if command -v convert >/dev/null 2>&1; then
    echo "ImageMagick trouvé, création des icônes PNG..."
    
    # Créer les dossiers
    mkdir -p "$BASE_DIR/mipmap-mdpi"
    mkdir -p "$BASE_DIR/mipmap-hdpi" 
    mkdir -p "$BASE_DIR/mipmap-xhdpi"
    mkdir -p "$BASE_DIR/mipmap-xxhdpi"
    mkdir -p "$BASE_DIR/mipmap-xxxhdpi"
    
    # Créer une icône simple bleu avec cercle blanc
    create_icon() {
        size=$1
        output=$2
        convert -size ${size}x${size} xc:"#007BFF" \
                -fill white -draw "circle $((size/2)),$((size/2)) $((size/2-size/8)),$((size/2))" \
                -fill "#007BFF" -draw "circle $((size/2)),$((size/2)) $((size/2-size/3)),$((size/2))" \
                "$output"
        echo "Créé: $output"
    }
    
    # Créer les icônes pour chaque densité
    create_icon 48 "$BASE_DIR/mipmap-mdpi/ic_launcher.png"
    create_icon 48 "$BASE_DIR/mipmap-mdpi/ic_launcher_round.png"
    
    create_icon 72 "$BASE_DIR/mipmap-hdpi/ic_launcher.png"
    create_icon 72 "$BASE_DIR/mipmap-hdpi/ic_launcher_round.png"
    
    create_icon 96 "$BASE_DIR/mipmap-xhdpi/ic_launcher.png"
    create_icon 96 "$BASE_DIR/mipmap-xhdpi/ic_launcher_round.png"
    
    create_icon 144 "$BASE_DIR/mipmap-xxhdpi/ic_launcher.png"
    create_icon 144 "$BASE_DIR/mipmap-xxhdpi/ic_launcher_round.png"
    
    create_icon 192 "$BASE_DIR/mipmap-xxxhdpi/ic_launcher.png"
    create_icon 192 "$BASE_DIR/mipmap-xxxhdpi/ic_launcher_round.png"
    
    # Remettre les mipmaps dans le manifest
    sed -i 's/android:icon="@drawable\/ic_launcher_legacy"/android:icon="@mipmap\/ic_launcher"/' "$BASE_DIR/../AndroidManifest.xml"
    sed -i '/android:label="@string\/app_name"/a\        android:roundIcon="@mipmap/ic_launcher_round"' "$BASE_DIR/../AndroidManifest.xml"
    
    echo "Toutes les icônes PNG ont été créées avec succès!"
else
    echo "ImageMagick non disponible, utilisation de l'icône drawable XML uniquement."
    echo "L'application fonctionnera parfaitement avec l'icône vectorielle."
fi