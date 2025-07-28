#!/usr/bin/env python3
import os
from PIL import Image, ImageDraw, ImageFont

def create_icon(size, path):
    # Créer une image avec fond bleu
    img = Image.new('RGBA', (size, size), (0, 123, 255, 255))
    draw = ImageDraw.Draw(img)
    
    # Dessiner un cercle blanc au centre
    margin = size // 8
    draw.ellipse([margin, margin, size-margin, size-margin], 
                 fill=(255, 255, 255, 255), outline=(255, 255, 255, 255))
    
    # Dessiner un point central bleu
    center_margin = size // 3
    draw.ellipse([center_margin, center_margin, size-center_margin, size-center_margin], 
                 fill=(0, 123, 255, 255), outline=(0, 123, 255, 255))
    
    # Sauvegarder
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path, 'PNG')
    print(f"Created: {path}")

# Créer les icônes pour différentes densités
base_path = "/home/mickael/Documents/Dev/tom/TomAssistant/app/src/main/res"

icon_sizes = {
    'mipmap-mdpi': 48,
    'mipmap-hdpi': 72,
    'mipmap-xhdpi': 96,
    'mipmap-xxhdpi': 144,
    'mipmap-xxxhdpi': 192
}

for folder, size in icon_sizes.items():
    folder_path = os.path.join(base_path, folder)
    create_icon(size, os.path.join(folder_path, 'ic_launcher.png'))
    create_icon(size, os.path.join(folder_path, 'ic_launcher_round.png'))

print("All icons created successfully!")