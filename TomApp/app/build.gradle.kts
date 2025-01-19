plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.jetbrains.kotlin.android)
    id("com.google.gms.google-services") // Ajout du plugin Google Services pour Firebase
}

android {
    namespace = "com.example.tomapp"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.example.tomapp"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"

        javaCompileOptions {
            annotationProcessorOptions {
                arguments += mapOf("room.incremental" to "true")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false // Désactiver la réduction de taille (ProGuard)
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
        debug {
            isMinifyEnabled = false // Ne pas réduire les fichiers en mode Debug
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_1_8 // Compatibilité source Java
        targetCompatibility = JavaVersion.VERSION_1_8 // Compatibilité cible Java
    }

    kotlinOptions {
        jvmTarget = "1.8" // Cible JVM 1.8 pour Kotlin
    }

    buildFeatures {
        viewBinding = true // Activer ViewBinding
    }

    packagingOptions {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

dependencies {
    // Dépendances AndroidX
    implementation("androidx.core:core-ktx:1.12.0") // Mise à jour vers la dernière version stable
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("com.google.android.material:material:1.9.0")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")

    // WebView
    implementation("androidx.webkit:webkit:1.9.0")

    // Firebase
    implementation(platform("com.google.firebase:firebase-bom:32.7.0")) // Dernière version du BOM
    implementation("com.google.firebase:firebase-messaging-ktx")
    implementation("com.google.firebase:firebase-analytics-ktx") // Ajout de Firebase Analytics

    // Kotlin
    implementation("org.jetbrains.kotlin:kotlin-stdlib:1.9.22")

    // Bluetooth et localisation
    implementation("com.google.android.gms:play-services-location:21.1.0")

    // Test
    testImplementation("junit:junit:4.13.2")
    androidTestImplementation("androidx.test.ext:junit:1.1.5")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.5.1")
}

// Ajout des services Google pour Firebase
apply(plugin = "com.google.gms.google-services")
