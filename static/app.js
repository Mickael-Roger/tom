document.addEventListener("DOMContentLoaded", () => {
    const promptInput = document.getElementById("prompt");
    const sendButton = document.getElementById("send-button");
    const speakButton = document.getElementById("speak-button");
    const chatBox = document.getElementById("chat-box");
    const autoSubmitCheckbox = document.getElementById("auto-submit");
    const languageSelect = document.getElementById("language-select");

    let userPosition = null; // Position GPS de l'utilisateur

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

    // Activer/désactiver le bouton Send
    promptInput.addEventListener("input", () => {
        sendButton.disabled = !promptInput.value.trim();
    });

    // Envoi du message lorsque Send est cliqué
    sendButton.addEventListener("click", () => {
        sendMessage();
    });

    // Fonction pour envoyer le message
    function sendMessage() {
        const message = promptInput.value.trim();
        if (!message) return;

        const selectedLanguage = languageSelect.value; // 'fr' ou 'en'
        addMessageToChat("user", message);

        const payload = {
            request: message,
            lang: selectedLanguage,
            position: userPosition // Ajout de la position GPS
        };

        fetch("/process", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        })
        .then(response => response.json())
        .then(data => {
            if (data.response) {
                addMessageToChat("bot", data.response);
                playResponseAudio(data.response, selectedLanguage);

                // Lecture de l'audio si le champ 'voice' est présent
                if (data.voice) {
                    playAudioFromBase64(data.voice);
                }
            }
        })
        .catch(error => {
            console.error("Erreur :", error);
            addMessageToChat("bot", "Une erreur est survenue.");
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

    // Fonction Text-to-Speech pour jouer la réponse
    function playResponseAudio(text, lang) {
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = lang === "fr" ? "fr-FR" : "en-US";
        speechSynthesis.speak(utterance);
    }

    // Fonction pour jouer un fichier audio MP3 encodé en base64
    function playAudioFromBase64(base64Audio) {
        const audio = new Audio("data:audio/mp3;base64," + base64Audio);
        audio.play().catch(error => {
            console.error("Erreur de lecture audio :", error);
        });
    }

    // Fonction Speech-to-Text pour le bouton Speak
    speakButton.addEventListener("click", () => {
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

    // Auto-submit lorsque Enter est pressé
    promptInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && autoSubmitCheckbox.checked) {
            sendMessage();
        }
    });

    // Mettre à jour la position toutes les 5 minutes
    setInterval(fetchUserPosition, 5 * 60 * 1000);
});

