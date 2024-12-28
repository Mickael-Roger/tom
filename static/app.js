document.addEventListener("DOMContentLoaded", () => {
    const promptInput = document.getElementById("prompt");
    const sendButton = document.getElementById("send-button");
    const speakButton = document.getElementById("speak-button");
    const chatBox = document.getElementById("chat-box");
    const autoSubmitCheckbox = document.getElementById("auto-submit");
    const languageSelect = document.getElementById("language-select");
    const resetButton = document.getElementById("reset-button");

    let userPosition = null; 
    let currentAudio = null; // Reference to the currently playing audio
    let isSpeaking = false; // Flag for TTS state

    // Tentative de récupération de la position GPS
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

    // Appel initial pour récupérer la position dès que la page est chargée
    fetchUserPosition();

    // Fonction pour vérifier si le client est un mobile Android avec Chrome et supporte TTS
    function isTTSAvailable() {
        //const isAndroid = /android/i.test(navigator.userAgent);
        //const isChrome = /chrome/i.test(navigator.userAgent) && !/edge/i.test(navigator.userAgent);
        //return isAndroid && isChrome && 'speechSynthesis' in window;
        return 'speechSynthesis' in window;
    }


    // Activer/désactiver le bouton Send
    promptInput.addEventListener("input", () => {
        sendButton.disabled = !promptInput.value.trim();
    });

    // Envoi du message lorsque Send est cliqué
    sendButton.addEventListener("click", () => {
        sendMessage();
    });


    function sendMessage() {
        const message = promptInput.value.trim();
        if (!message) return;
    
        const selectedLanguage = languageSelect.value; // 'fr' ou 'en'
        addMessageToChat("user", message);
    
        const payload = {
            request: message,
            lang: selectedLanguage,
            position: userPosition, // Ajout de la position GPS
            tts: isTTSAvailable() // Ajout du champ tts
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
    
                // Lecture de l'audio si le champ 'voice' est présent et tts est false
                if (data.voice && !payload.tts) {
                    playAudioFromBase64(data.voice);
                } else if (payload.tts) {
                    // Si tts est true, lire le texte localement
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

    // Fonction pour ajouter un message au chat
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
        const selectedLanguage = languageSelect.value;

        recognition.lang = selectedLanguage === "fr" ? "fr-FR" : "en-US";
        recognition.start();

        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            promptInput.value = transcript;
            sendButton.disabled = !transcript.trim();

            // Envoi automatique si auto-submit est coché
            if (autoSubmitCheckbox.checked) {
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
                    const chatBox = document.getElementById("chat-box");
                    chatBox.innerHTML = "";
                } else {
                    console.error("Failed to reset:", data.message);
                }
            })
            .catch(error => {
                console.error("Error during reset:", error);
            });
    });

    // Auto-submit lorsque Enter est pressé
    promptInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && autoSubmitCheckbox.checked) {
            sendMessage();
        }
    });

    // Mettre à jour la position toutes les 5 minutes
    setInterval(fetchUserPosition, 5 * 60 * 1000);
});

