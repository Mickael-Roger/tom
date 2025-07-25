document.addEventListener("DOMContentLoaded", () => {
    const promptInput = document.getElementById("prompt");
    const sendButton = document.getElementById("send-button");
    const speakButton = document.getElementById("speak-button");
    const chatBox = document.getElementById("chat-box");
    const resetButton = document.getElementById("reset-button");
    const gearIcon = document.getElementById("gear-icon");
    const configBox = document.getElementById("config-box");
    const autoSubmitConfig = document.getElementById("auto-submit-config");
    const soundConfig = document.getElementById("sound-config");
    const languageConfigEn = document.getElementById("language-config-en");
    const languageConfigFr = document.getElementById("language-config-fr");
    const tasksIcon = document.getElementById("tasks-icon");
    const tasksBox = document.getElementById("tasks-box");
    const tasksCounter = document.getElementById("tasks-counter");
    const tasksList = document.getElementById("tasks-list");

    let tasks = [];

    let lastDisplayedId = 0;

    // Auto-reset session history on page load
    fetch("/reset", { method: "POST" })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                console.log("Session history reset automatically on page load");
            } else {
                console.error("Failed to reset session history:", data.message);
            }
        })
        .catch(error => {
            console.error("Error during auto-reset:", error);
        });

    let userPosition = null;
    let currentAudio = null; // Reference to the currently playing audio
    let isSpeaking = false; // Flag for TTS state
    let autoSubmitEnabled = false; // Auto-submit state
    let selectedLanguage = "fr"; // Default language
    let soundEnabled = true; // Sound state (default: enabled)

    // Settings persistence functions
    function saveSettings() {
        const settings = {
            autoSubmitEnabled,
            selectedLanguage,
            soundEnabled
        };
        localStorage.setItem('tomAppSettings', JSON.stringify(settings));
    }

    function loadSettings() {
        const saved = localStorage.getItem('tomAppSettings');
        if (saved) {
            try {
                const settings = JSON.parse(saved);
                autoSubmitEnabled = settings.autoSubmitEnabled !== undefined ? settings.autoSubmitEnabled : false;
                selectedLanguage = settings.selectedLanguage || "fr";
                soundEnabled = settings.soundEnabled !== undefined ? settings.soundEnabled : true;
                
                // Update UI to reflect loaded settings
                autoSubmitConfig.classList.toggle("active", autoSubmitEnabled);
                soundConfig.classList.toggle("active", soundEnabled);
                soundConfig.textContent = soundEnabled ? "🔊 Sound" : "🔇 Mute";
                updateLanguageConfig();
            } catch (e) {
                console.error("Error loading settings:", e);
            }
        }
    }

    // Toggle configuration box visibility
    gearIcon.addEventListener("click", () => {
        configBox.classList.toggle("hidden");
    });

    // Handle auto-submit configuration
    autoSubmitConfig.addEventListener("click", () => {
        autoSubmitEnabled = !autoSubmitEnabled;
        autoSubmitConfig.classList.toggle("active", autoSubmitEnabled);
        saveSettings();
    });

    // Handle sound configuration
    soundConfig.addEventListener("click", () => {
        soundEnabled = !soundEnabled;
        soundConfig.classList.toggle("active", soundEnabled);
        soundConfig.textContent = soundEnabled ? "🔊 Sound" : "🔇 Mute";
        saveSettings();
    });

    // Handle language configuration
    languageConfigEn.addEventListener("click", () => {
        selectedLanguage = "en";
        updateLanguageConfig();
        saveSettings();
    });

    languageConfigFr.addEventListener("click", () => {
        selectedLanguage = "fr";
        updateLanguageConfig();
        saveSettings();
    });

    // Update language configuration appearance
    function updateLanguageConfig() {
        languageConfigEn.classList.toggle("active", selectedLanguage === "en");
        languageConfigFr.classList.toggle("active", selectedLanguage === "fr");
    }

    // Load saved settings and update UI
    loadSettings();
    
    // Initial updates
    updateLanguageConfig();

    // Activate/deactivate send button based on input
    promptInput.addEventListener("input", () => {
        sendButton.disabled = !promptInput.value.trim();
    });

    // Send message when Send button is clicked
    sendButton.addEventListener("click", () => {
        sendMessage();
    });

    // Send message when Enter is pressed (if auto-submit is enabled)
    promptInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && autoSubmitEnabled) {
            sendMessage();
        }
    });


    // Function to send the message
    function sendMessage() {
        const message = promptInput.value.trim();
        if (!message) return;
    
        // Ajouter le message utilisateur à la chat box
        addMessageToChat("user", message);
    
        const clientType = window.matchMedia('(display-mode: standalone)').matches ? 'pwa' : 'web';

        const payload = {
            request: message,
            lang: selectedLanguage,
            position: userPosition,
            tts: isTTSAvailable(),
            client_type: clientType
        };
    
        // Envoyer la requête à /process sans attendre sa réponse
        const processRequest = fetch("/process", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
    
        // Fetch immédiat de /tasks pour gérer les nouveaux messages de tâches
        fetch("/tasks", { method: "GET" })
            .then(response => response.json())
            .then(taskData => {
                // Afficher et lire les messages de tâches
                displayAndReadTaskMessage(taskData);
    
                // Une fois les messages de tâches traités, gérer la réponse de /process
                processRequest
                    .then(response => {
                        if (!response.ok) {
                            throw new Error("Network response was not ok");
                        }
                        return response.json();
                    })
                    .then(data => {
                        // Afficher la réponse de /process après les messages de tâches
                        if (data.response) {
                            addMessageToChat("bot", data.response);
    
                            // Jouer l'audio si disponible
                            if (soundEnabled && data.voice && !payload.tts) {
                                playAudioFromBase64(data.voice);
                            } else if (soundEnabled && payload.tts) {
                                const sanitizedText = sanitizeText(data.response);
                                speakText(sanitizedText, selectedLanguage);
                            }
                        }
                    })
                    .catch(error => {
                        console.error("Erreur lors de l'appel à /process :", error);
    
                        // En cas d'échec, effectuer un reset
                        fetch("/reset", { method: "POST" })
                            .then(response => response.json())
                            .then(data => {
                                if (data.success) {
                                    const failureMessage = selectedLanguage === "en" ? "Failure" : "Échec";
                                    addMessageToChat("bot", failureMessage);
                                } else {
                                    console.error("Échec du reset :", data.message);
                                }
                            })
                            .catch(resetError => {
                                console.error("Erreur lors du reset :", resetError);
                            });
                    });
            })
            .catch(error => {
                console.error("Erreur lors de la récupération des tâches :", error);
            });
    
        // Réinitialiser le champ de saisie et désactiver le bouton d'envoi
        promptInput.value = "";
        sendButton.disabled = true;
    }





    function sanitizeText(text){
        const openPattern = /\[open:(.+)\]/;
        displayText = text.replace(openPattern, "").trim();
        sanitizedText = DOMPurify.sanitize(displayText);

        return sanitizedText;

    }

    function renderMarkdown(text) {
        // Parse markdown and sanitize the result
        const htmlContent = marked.parse(text);
        return DOMPurify.sanitize(htmlContent);
    }

    // Function to add a message to the chat
    function addMessageToChat(sender, text) {
        const messageDiv = document.createElement("div");
        messageDiv.classList.add("message", sender);

        // Check for custom commands
        const openPattern = /\[open:(.+)\]/;
        const matchopen = text.match(openPattern);

        let processedText = text;
        if (matchopen && matchopen[1]) {
            const url = matchopen[1];
            processedText = text.replace(openPattern, "").trim();
            
            // Validate the URL
            if (isValidUrl(url)) {
                window.open(url, "_blank");
            } else {
                console.warn("Invalid URL:", url);
            }
        }

        // Render markdown for bot messages, plain text for user messages
        if (sender === "bot") {
            messageDiv.innerHTML = renderMarkdown(processedText);
        } else {
            messageDiv.innerHTML = DOMPurify.sanitize(processedText);
        }

        chatBox.appendChild(messageDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    // Helper function to validate URLs
    function isValidUrl(url) {
        try {
            new URL(url); // This will throw an error for invalid URLs
            return true;
        } catch (e) {
            return false;
        }
    }

    // Play Base64 MP3 and stop if speak button is clicked
    function playAudioFromBase64(base64Audio) {
        if (currentAudio) {
            currentAudio.pause(); // Stop current audio if playing
            currentAudio = null;
        }

        currentAudio = new Audio("data:audio/mp3;base64," + base64Audio);
        currentAudio.play().catch(error => {
            console.error("Erreur de lecture audio :", error);
        });

        currentAudio.onended = () => {
            currentAudio = null; // Reset when the audio finishes
        };
    }

    // Use local TTS to speech
//    function speakText(text, language) {
//        if (isSpeaking) {
//            window.speechSynthesis.cancel(); // Stop any ongoing TTS
//            isSpeaking = false;
//        }
//
//        const utterance = new SpeechSynthesisUtterance(text);
//        utterance.lang = language === "fr" ? "fr-FR" : "en-US";
//
//        utterance.onstart = () => {
//            isSpeaking = true;
//        };
//
//        utterance.onend = () => {
//            isSpeaking = false;
//        };
//
//        window.speechSynthesis.speak(utterance);
//    }

    function speakText(text, language) {
        if (isSpeaking) {
            // Arrêter tout TTS en cours
            if (window.speechSynthesis) {
                window.speechSynthesis.cancel();
            }
            if (window.AndroidTTS) {
                // AndroidTTS ne dispose pas de fonction pour annuler, mais on peut gérer via isSpeaking
                console.log("Stopping Android TTS...");
            }
            isSpeaking = false;
        }

        // Utilisation de SpeechSynthesis si disponible
        if (window.speechSynthesis) {
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.lang = language === "fr" ? "fr-FR" : "en-US";

            utterance.onstart = () => {
                isSpeaking = true;
            };

            utterance.onend = () => {
                isSpeaking = false;
            };

            window.speechSynthesis.speak(utterance);
        } 
        // Sinon, utilisation de l'API AndroidTTS
        else if (window.AndroidTTS) {
            const androidLanguage = language === "fr" ? "fr-FR" : "en-US";

            try {
                isSpeaking = true; // Marquer comme en cours de parole
                // Utilisation de AndroidTTS avec les paramètres textuels et linguistiques
                window.AndroidTTS.speak(text, androidLanguage);
                console.log(`Android TTS: Speaking "${text}" in ${androidLanguage}`);

                // Simuler les événements onstart et onend avec un délai basé sur la longueur du texte
                setTimeout(() => {
                    isSpeaking = false; // Fin du TTS
                    console.log("Android TTS finished speaking.");
                }, Math.max(1000, text.length * 100)); // Estimation du temps basé sur 100 ms par caractère
            } catch (error) {
                console.error("Error with Android TTS:", error);
                isSpeaking = false;
            }
        } else {
            console.error("No TTS engine available.");
        }
    }

    // Handle Speak button click
    speakButton.addEventListener("click", () => {
        // Stop audio playback if active
        if (currentAudio) {
            currentAudio.pause();
            currentAudio = null;
        }
    
        // Stop TTS if active
        if (isSpeaking) {
            window.speechSynthesis.cancel();
            isSpeaking = false;
        }
    
        // Start speech recognition
        const recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
        recognition.lang = selectedLanguage === "fr" ? "fr-FR" : "en-US";
        recognition.start();
    
        // Change button color to orange when recording starts
        speakButton.style.backgroundColor = "#ffa500"; // Orange color
    
        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            promptInput.value = transcript;
            sendButton.disabled = !transcript.trim();
    
            // Auto-submit if enabled
            if (autoSubmitEnabled) {
                sendMessage();
            }
    
            // Reset button color after recording ends
            speakButton.style.backgroundColor = "#007bff"; // Original blue color
        };
    
        recognition.onerror = (event) => {
            console.error("Erreur de reconnaissance vocale :", event.error);
            // Reset button color if there's an error
            speakButton.style.backgroundColor = "#007bff"; // Original blue color
        };
    
        recognition.onend = () => {
            // Reset button color when recording ends
            speakButton.style.backgroundColor = "#007bff"; // Original blue color
        };
    });

    // Handle Reset button click
    resetButton.addEventListener("click", () => {
        fetch("/reset", { method: "POST" })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Clear the chat box content
                    chatBox.innerHTML = "";
    
                    // Fetch tasks après le reset
                    fetch("/tasks", { method: "GET" })
                        .then(response => response.json())
                        .then(taskData => {
                            displayAndReadTaskMessage(taskData);
                        })
                        .catch(error => {
                            console.error("Erreur lors de la récupération des tâches après reset :", error);
                        });
                } else {
                    console.error("Failed to reset:", data.message);
                }
            })
            .catch(error => {
                console.error("Error during reset:", error);
            });
    });

    // Fetch user position periodically
    fetchUserPosition();
    setInterval(fetchUserPosition, 30 * 1000);

    // Function to fetch user position
    function fetchUserPosition() {
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    userPosition = {
                        latitude: position.coords.latitude,
                        longitude: position.coords.longitude
                    };
                },
                (error) => {
                    console.warn("Impossible de récupérer la position :", error.message);
                    userPosition = null; // Position non disponible
                }
            );
        } else {
            console.warn("La géolocalisation n'est pas supportée par ce navigateur.");
            userPosition = null;
        }
    }

    // Function to check if TTS is available
    function isTTSAvailable() {
        return 'speechSynthesis' in window  || 'AndroidTTS' in window;;
    }


    // Toggle tasks box visibility
    tasksIcon.addEventListener("click", () => {
        if (tasksBox.classList.contains("hidden")) {
            tasksBox.classList.remove("hidden");
            console.log("Tasks box shown");
        } else {
            tasksBox.classList.add("hidden");
            console.log("Tasks box hidden");
        }
    });

    // Fetch background tasks periodically
    setInterval(fetchBackgroundTasks, 60000); // Every 60 seconds
    fetchBackgroundTasks();

    function fetchBackgroundTasks() {
        fetch("/tasks", { method: "GET" })
            .then(response => response.json())
            .then(data => {
                if (data.background_tasks) {
                    tasks = data.background_tasks;
                    updateTasksUI(); // Met à jour l'interface pour les tâches
                    displayAndReadTaskMessage(data); // Affiche et lit le message et ID
                }
            })
            .catch(error => console.error("Error fetching tasks:", error));
    }

    // Fonction pour détecter un clic en dehors d'un élément
    function closeOnClickOutside(boxElement, toggleElement) {
        document.addEventListener("click", (event) => {
            const isClickInsideBox = boxElement.contains(event.target);
            const isClickOnToggle = toggleElement.contains(event.target);
    
            if (!isClickInsideBox && !isClickOnToggle) {
                boxElement.classList.add("hidden"); // Cacher la boîte si clic à l'extérieur
            }
        });
    }
    
    // Appliquer la logique pour la boîte de configuration
    closeOnClickOutside(configBox, gearIcon);
    
    // Appliquer la logique pour la boîte des tâches
    closeOnClickOutside(tasksBox, tasksIcon);

    function updateTasksUI() {
        // Update counter
        tasksCounter.textContent = tasks.length;

        // Update tasks list
        tasksList.innerHTML = ""; // Clear existing items
        tasks.forEach(task => {
            const taskItem = document.createElement("div");
            taskItem.className = "tasks-list-item";

            const moduleName = document.createElement("span");
            moduleName.className = "module-name";
            moduleName.textContent = task.module;

            const status = document.createElement("span");
            status.className = "status";
            status.textContent = task.status;

            taskItem.appendChild(moduleName);
            taskItem.appendChild(status);

            tasksList.appendChild(taskItem);
        });
    }

    // Tasks messages
    function displayAndReadTaskMessage(data) {
        const message = data.message;
        const id = data.id;
    
        // Afficher et lire le message uniquement si l'ID est supérieur au dernier affiché
        if (id > lastDisplayedId) {
            lastDisplayedId = id; // Mettre à jour le dernier ID traité
    
            // Ajouter le message à la chat box
            if (message) {
                addMessageToChat("bot", message);
    
                // Lire le message avec TTS si activé
                if (soundEnabled) {
                    speakText(message, selectedLanguage);
                }
            }
        } else {
            return;
        }
    }

});
