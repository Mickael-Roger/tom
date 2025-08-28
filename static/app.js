document.addEventListener("DOMContentLoaded", () => {
    const promptInput = document.getElementById("prompt");
    const sendButton = document.getElementById("send-button");
    const speakButton = document.getElementById("speak-button");
    const chatBox = document.getElementById("chat-box");
    const resetButton = document.getElementById("reset-button");
    const gearIconHeader = document.getElementById("gear-icon-header");
    const configBox = document.getElementById("config-box");
    const autoSubmitConfig = document.getElementById("auto-submit-config");
    const soundConfig = document.getElementById("sound-config");
    const tasksBox = document.getElementById("tasks-box");
    const tasksList = document.getElementById("tasks-list");
    const tasksIconHeader = document.getElementById("tasks-icon-header");
    const tasksCounterHeader = document.getElementById("tasks-counter-header");
    const moduleStatusToggle = document.getElementById("module-status-toggle");
    const moduleStatusList = document.getElementById("module-status-list");
    const moduleInfoModal = document.getElementById("module-info-modal");
    const modalCloseButton = document.getElementById("modal-close-button");
    const moduleStatusArrow = document.getElementById("module-status-arrow");

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
    let isSpeaking = false; // Flag for TTS state
    let autoSubmitEnabled = false; // Auto-submit state
    let soundEnabled = true; // Sound state (default: enabled)

    // Settings persistence functions
    function saveSettings() {
        const settings = {
            autoSubmitEnabled,
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
                soundEnabled = settings.soundEnabled !== undefined ? settings.soundEnabled : true;
                
                // Update UI to reflect loaded settings
                autoSubmitConfig.classList.toggle("active", autoSubmitEnabled);
                soundConfig.classList.toggle("active", soundEnabled);
                soundConfig.textContent = soundEnabled ? "🔊 Sound" : "🔇 Mute";
            } catch (e) {
                console.error("Error loading settings:", e);
            }
        }
    }

    // Toggle configuration box visibility and fetch module status
    gearIconHeader.addEventListener("click", () => {
        configBox.classList.toggle("hidden");

        // If the box is now visible, fetch the status
        if (!configBox.classList.contains("hidden")) {
            fetchModuleStatus();
        } else {
            moduleStatusList.classList.add("hidden");
            moduleStatusArrow.textContent = "▼";
        }
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

    moduleStatusToggle.addEventListener("click", () => {
        moduleStatusList.classList.toggle("hidden");
        if (moduleStatusList.classList.contains("hidden")) {
            moduleStatusArrow.textContent = "▼";
        } else {
            moduleStatusArrow.textContent = "▲";
        }
    });



    // Load saved settings and update UI
    loadSettings();
    

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
            position: userPosition,
            client_type: clientType,
            sound_enabled: soundEnabled
        };
    
        // Envoyer la requête à /process sans attendre sa réponse
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 180000); // 3 minutes timeout
        
        const processRequest = fetch("/process", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
            signal: controller.signal
        }).finally(() => clearTimeout(timeoutId));
    
        // Fetch immédiat de /tasks pour gérer les nouveaux messages de tâches
        fetch("/tasks", { method: "GET" })
            .then(response => response.json())
            .then(taskData => {
                // Traiter les messages de tâches (sans affichage dans le chat)
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
    
                            // Use local TTS if enabled
                            if (soundEnabled && isTTSAvailable()) {
                                // Use response_tts if available (server-synthesized), otherwise fallback to sanitized response
                                const textToSpeak = data.response_tts || sanitizeText(data.response);
                                speakText(textToSpeak);
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
                                    const failureMessage = "Échec";
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



    // Handle Speak button click
    speakButton.addEventListener("click", () => {
        // Stop TTS if active
        if (isSpeaking) {
            if (window.speechSynthesis) {
                window.speechSynthesis.cancel();
            }
            isSpeaking = false;
        }
    
        // Start speech recognition
        const recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
        recognition.lang = "fr-FR";
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

    // Use local TTS to speech
    function speakText(text) {
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
            utterance.lang = "fr-FR";

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
            const androidLanguage = "fr-FR";

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

    // Function to check if TTS is available
    function isTTSAvailable() {
        return 'speechSynthesis' in window || 'AndroidTTS' in window;
    }

    // Toggle tasks box visibility
    function toggleTasksBox() {
        if (tasksBox.classList.contains("hidden")) {
            tasksBox.classList.remove("hidden");
            console.log("Tasks box shown");
        } else {
            tasksBox.classList.add("hidden");
            console.log("Tasks box hidden");
        }
    }

    tasksIconHeader.addEventListener("click", toggleTasksBox);

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
                    displayAndReadTaskMessage(data); // Traite l'ID (sans affichage dans le chat)
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
    closeOnClickOutside(configBox, gearIconHeader);
    
    // Appliquer la logique pour la boîte des tâches
    closeOnClickOutside(tasksBox, tasksIconHeader);

    function updateTasksUI() {
        // Update counter
        tasksCounterHeader.textContent = tasks.length;
        
        // Show/hide counter based on task count
        tasksCounterHeader.style.display = tasks.length > 0 ? 'flex' : 'none';

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

        // Update notification ticker
        updateNotificationTicker();
    }

    // Tasks messages - Ne plus afficher le message dans le chat
    function displayAndReadTaskMessage(data) {
        const id = data.id;
    
        // Mettre à jour l'ID uniquement si supérieur au dernier traité
        if (id > lastDisplayedId) {
            lastDisplayedId = id; // Mettre à jour le dernier ID traité
        }
    }

    // Update notification ticker with scrolling notifications
    function updateNotificationTicker() {
        const tickerContent = document.getElementById("ticker-content");
        
        if (tasks.length === 0) {
            tickerContent.innerHTML = '<span class="ticker-text">Aucune notification</span>';
        } else {
            // Create scrolling text with all notifications, module names in bold
            let notificationText = "";
            tasks.forEach((task, index) => {
                notificationText += `<span class="ticker-module">${task.module}</span>: ${task.status}`;
                if (index < tasks.length - 1) {
                    notificationText += "    •    ";
                }
            });
            
            // Simple single display without repetition
            tickerContent.innerHTML = `<span class="ticker-text">${notificationText}</span>`;
        }
    }

    // Fetch and display module statuses
    function fetchModuleStatus() {
        moduleStatusList.innerHTML = "<p>Fetching statuses...</p>"; // Debugging text

        fetch("/status")
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! Status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                moduleStatusList.innerHTML = ""; // Clear previous statuses
                if (data.modules && data.modules.length > 0) {
                    data.modules.forEach(module => {
                        const button = document.createElement("button");
                        button.textContent = module.name;
                        button.className = "module-status-button";
                        if (module.status === "connected") {
                            button.classList.add("status-ok");
                        } else {
                            button.classList.add("status-error");
                        }
                        button.addEventListener("click", () => showModuleInfo(module));
                        moduleStatusList.appendChild(button);
                    });
                } else {
                    moduleStatusList.textContent = "No modules found."; // Debugging text
                }
            })
            .catch(error => {
                console.error("Error fetching module status:", error);
                moduleStatusList.textContent = "Error fetching data."; // Debugging text
            });
    }

    // Show modal with module details
    function showModuleInfo(module) {
        document.getElementById("modal-module-name").textContent = module.name;
        document.getElementById("modal-module-status").textContent = module.status;
        document.getElementById("modal-module-description").textContent = module.description;
        document.getElementById("modal-module-llm").textContent = module.llm;
        document.getElementById("modal-module-tools").textContent = module.tools_count;
        document.getElementById("modal-module-enabled").textContent = module.enabled ? 'Yes' : 'No';
        
        moduleInfoModal.classList.add("visible");
    }

    // Close modal
    function closeModal() {
        moduleInfoModal.classList.remove("visible");
    }

    modalCloseButton.addEventListener("click", closeModal);
    moduleInfoModal.addEventListener("click", (event) => {
        if (event.target === moduleInfoModal) {
            closeModal();
        }
    });

});