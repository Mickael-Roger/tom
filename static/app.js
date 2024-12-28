document.addEventListener("DOMContentLoaded", () => {
    const promptInput = document.getElementById("prompt");
    const sendButton = document.getElementById("send-button");
    const speakButton = document.getElementById("speak-button");
    const chatBox = document.getElementById("chat-box");
    const resetButton = document.getElementById("reset-button");
    const gearIcon = document.getElementById("gear-icon");
    const configBox = document.getElementById("config-box");
    const autoSubmitConfig = document.getElementById("auto-submit-config");
    const languageConfigEn = document.getElementById("language-config-en");
    const languageConfigFr = document.getElementById("language-config-fr");

    let userPosition = null;
    let currentAudio = null; // Reference to the currently playing audio
    let isSpeaking = false; // Flag for TTS state
    let autoSubmitEnabled = false; // Auto-submit state
    let selectedLanguage = "fr"; // Default language

    // Toggle configuration box visibility
    gearIcon.addEventListener("click", () => {
        configBox.classList.toggle("hidden");
    });

    // Handle auto-submit configuration
    autoSubmitConfig.addEventListener("click", () => {
        autoSubmitEnabled = !autoSubmitEnabled;
        autoSubmitConfig.classList.toggle("active", autoSubmitEnabled);
    });

    // Handle language configuration
    languageConfigEn.addEventListener("click", () => {
        selectedLanguage = "en";
        updateLanguageConfig();
    });

    languageConfigFr.addEventListener("click", () => {
        selectedLanguage = "fr";
        updateLanguageConfig();
    });

    // Update language configuration appearance
    function updateLanguageConfig() {
        languageConfigEn.classList.toggle("active", selectedLanguage === "en");
        languageConfigFr.classList.toggle("active", selectedLanguage === "fr");
    }

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

        addMessageToChat("user", message);

        const payload = {
            request: message,
            lang: selectedLanguage,
            position: userPosition, // GPS position
            tts: isTTSAvailable() // TTS availability
        };

        fetch("/process", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            if (data.response) {
                addMessageToChat("bot", data.response);

                // Play audio if voice is provided and TTS is not available
                if (data.voice && !payload.tts) {
                    playAudioFromBase64(data.voice);
                } else if (payload.tts) {
                    // Use TTS if available
                    speakText(data.response, selectedLanguage);
                }
            }
        })
        .catch(error => {
            console.error("Erreur :", error);
            // Call /reset on failure
            fetch("/reset", { method: "POST" })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        // Add failure message to chat based on selected language
                        const failureMessage = selectedLanguage === "en" ? "Failure" : "Echec";
                        addMessageToChat("bot", failureMessage);
                    } else {
                        console.error("Failed to reset:", data.message);
                    }
                })
                .catch(resetError => {
                    console.error("Error during reset:", resetError);
                });
        });

        promptInput.value = "";
        sendButton.disabled = true;
    }

    // Function to add a message to the chat
    function addMessageToChat(sender, text) {
        const messageDiv = document.createElement("div");
        messageDiv.classList.add("message", sender);
        messageDiv.textContent = text;
        chatBox.appendChild(messageDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
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
    function speakText(text, language) {
        if (isSpeaking) {
            window.speechSynthesis.cancel(); // Stop any ongoing TTS
            isSpeaking = false;
        }

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

        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            promptInput.value = transcript;
            sendButton.disabled = !transcript.trim();

            // Auto-submit if enabled
            if (autoSubmitEnabled) {
                sendMessage();
            }
        };

        recognition.onerror = (event) => {
            console.error("Erreur de reconnaissance vocale :", event.error);
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
                } else {
                    console.error("Failed to reset:", data.message);
                }
            })
            .catch(error => {
                console.error("Error during reset:", error);
            });
    });

    // Fetch user position periodically
    setInterval(fetchUserPosition, 5 * 60 * 1000);

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
        return 'speechSynthesis' in window;
    }
});
