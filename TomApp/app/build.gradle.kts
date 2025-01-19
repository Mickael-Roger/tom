plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.jetbrains.kotlin.android)
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
            isMinifyEnabled = false // Ne pas réduire les fichiers dans Debug
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_1_8 // Compatibilité source Java
        targetCompatibility = JavaVersion.VERSION_1_8 // Compatibilité cible Java
    }

    kotlinOptions {
        jvmTarget = "1.8" // Cible JVM 1.8 pour Kotlin
    }

    // Activer les configurations de fonctionnalités supplémentaires
    buildFeatures {
        viewBinding = true // Activer le ViewBinding si nécessaire
    }
}

dependencies {
    // Dépendances AndroidX
    //implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("com.google.android.material:material:1.9.0")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")

    // WebView si vous en avez besoin
    implementation("androidx.webkit:webkit:1.6.0")

    // Dépendances Firebase si vous utilisez Firebase
    implementation(platform("com.google.firebase:firebase-bom:32.2.3"))
    implementation("com.google.firebase:firebase-messaging-ktx")

    // Kotlin
    implementation("org.jetbrains.kotlin:kotlin-stdlib:1.9.0")

    // Test
    testImplementation("junit:junit:4.13.2")
    androidTestImplementation("androidx.test.ext:junit:1.1.5")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.5.1")
}