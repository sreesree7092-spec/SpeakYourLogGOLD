
document.addEventListener("DOMContentLoaded", () => {
    // Password show / hide
    document.querySelectorAll('input[type="password"]').forEach((input) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "password-toggle";
        button.textContent = "Show password";

        button.addEventListener("click", () => {
            const hidden = input.type === "password";
            input.type = hidden ? "text" : "password";
            button.textContent = hidden ? "Hide password" : "Show password";
        });

        input.insertAdjacentElement("afterend", button);
    });

    // Daily log character counter
    const logText = document.getElementById("log_text");

    if (logText) {
        const counter = document.createElement("p");
        counter.className = "form-note";
        logText.insertAdjacentElement("afterend", counter);

        const updateCount = () => {
            counter.textContent = `${logText.value.length} characters`;
        };

        logText.addEventListener("input", updateCount);
        updateCount();
    }

    // Language
    const pageLanguage = document.documentElement.lang || "en";
    const isTamilPage = pageLanguage.toLowerCase().startsWith("ta");
    const speechLanguage = isTamilPage ? "ta-IN" : "en-IN";

    // Speech recognition
    const SpeechRecognition =
        window.SpeechRecognition || window.webkitSpeechRecognition;

    let activeRecognition = null;

    function stopListening(statusElement) {
        if (activeRecognition) {
            const recognition = activeRecognition;
            activeRecognition = null;

            try {
                recognition.stop();
            } catch (error) {
                console.warn("Microphone stop failed:", error);
            }
        }

        if (statusElement) {
            statusElement.textContent = "Microphone stopped.";
        }
    }

    function startListening(textArea, statusElement, startButton, onFinalText) {
        if (!SpeechRecognition) {
            statusElement.textContent =
                "Speech recognition is unavailable. Please use Google Chrome.";
            return;
        }

        if (activeRecognition) {
            try {
                activeRecognition.stop();
            } catch (error) {
                console.warn(error);
            }
            activeRecognition = null;
        }

        if ("speechSynthesis" in window) {
            window.speechSynthesis.cancel();
        }

        const recognition = new SpeechRecognition();
        recognition.lang = speechLanguage;
        recognition.continuous = true;
        recognition.interimResults = false;
        activeRecognition = recognition;

        recognition.onstart = () => {
            statusElement.textContent = speechLanguage === "ta-IN"
                ? "கேட்கிறேன்... இப்போது பேசுங்கள்."
                : "Listening... Speak now.";
            startButton.disabled = true;
        };

        recognition.onresult = (event) => {
            let spokenText = "";

            for (let i = event.resultIndex; i < event.results.length; i++) {
                if (event.results[i].isFinal) {
                    spokenText += event.results[i][0].transcript + " ";
                }
            }

            spokenText = spokenText.trim();
            if (!spokenText) return;

            if (typeof onFinalText === "function") {
                onFinalText(spokenText);
            } else {
                textArea.value += (textArea.value.trim() ? " " : "") + spokenText;
                textArea.dispatchEvent(new Event("input", { bubbles: true }));
            }
        };

        recognition.onerror = (event) => {
            statusElement.textContent =
                `Microphone issue: ${event.error}. Check microphone permission.`;
        };

        recognition.onend = () => {
            startButton.disabled = false;
            if (activeRecognition === recognition) {
                activeRecognition = null;
            }
        };

        try {
            recognition.start();
        } catch (error) {
            statusElement.textContent = "Could not start microphone. Try again.";
            startButton.disabled = false;
            activeRecognition = null;
        }
    }

    // Daily log microphone
    const startLogMic = document.getElementById("start-log-mic");
    const stopLogMic = document.getElementById("stop-log-mic");
    const logStatus = document.getElementById("log-voice-status");

    if (startLogMic && stopLogMic && logStatus && logText) {
        startLogMic.addEventListener("click", () => {
            startListening(logText, logStatus, startLogMic);
        });

        stopLogMic.addEventListener("click", () => {
            stopListening(logStatus);
        });
    }

    // AI chat elements
    const chatForm = document.getElementById("ai-chat-form");
    const aiMessage = document.getElementById("ai-message");
    const chatBox = document.getElementById("ai-chat");
    const aiStatus = document.getElementById("ai-voice-status");
    const aiMic = document.getElementById("start-ai-mic");
    const stopAiMic = document.getElementById("stop-ai-mic");
    const readAnswerButton = document.getElementById("read-ai-answer");
    const sendButton = document.getElementById("send-ai-message");

    let lastAnswer = "";
    let greetingStarted = false;

    // Display Markdown safely in AI messages
    function addChatMessage(role, text) {
        if (!chatBox) return;

        const wrapper = document.createElement("div");
        wrapper.className = role === "assistant"
            ? "chat-message assistant-message"
            : "chat-message user-message";

        const heading = document.createElement("strong");
        heading.textContent = role === "assistant" ? "Speak Your Log AI" : "You";

        const content = document.createElement("div");
        content.className = "chat-message-content";

        const messageText = String(text ?? "");

        if (
            role === "assistant" &&
            typeof marked !== "undefined" &&
            typeof DOMPurify !== "undefined"
        ) {
            content.innerHTML = DOMPurify.sanitize(
                marked.parse(messageText, { breaks: true, gfm: true }),
                { USE_PROFILES: { html: true } }
            );

            content.querySelectorAll("a").forEach((link) => {
                link.target = "_blank";
                link.rel = "noopener noreferrer";
            });
        } else {
            content.textContent = messageText;
        }

        wrapper.append(heading, content);
        chatBox.appendChild(wrapper);
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    // Remove Markdown formatting for voice playback
    function cleanTextForSpeech(text) {
        let clean = String(text ?? "");

        clean = clean.replace(/```[\s\S]*?```/g, " Code example omitted. ");
        clean = clean.replace(/`([^`]+)`/g, "$1");
        clean = clean.replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1");
        clean = clean.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");
        clean = clean.replace(/^#{1,6}\s*/gm, "");
        clean = clean.replace(/\*\*(.*?)\*\*/g, "$1");
        clean = clean.replace(/__(.*?)__/g, "$1");
        clean = clean.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, "$1");
        clean = clean.replace(/^\s*[-*+]\s+/gm, "");
        clean = clean.replace(/^\s*\d+\.\s+/gm, "");
        clean = clean.replace(/^\s*[-*_]{3,}\s*$/gm, "");
        clean = clean.replace(/\n{3,}/g, "\n\n");

        return clean.trim();
    }

    // Speak AI answer
    function speakText(text) {
        if (!("speechSynthesis" in window)) {
            if (aiStatus) {
                aiStatus.textContent = "Voice playback is not supported.";
            }
            return;
        }

        window.speechSynthesis.cancel();

        const utterance = new SpeechSynthesisUtterance(
            cleanTextForSpeech(text)
        );
        utterance.lang = speechLanguage;
        utterance.rate = 0.9;

        const voices = window.speechSynthesis.getVoices();
        const matchingVoice = voices.find((voice) =>
            voice.lang.toLowerCase() === speechLanguage.toLowerCase()
        );

        if (matchingVoice) utterance.voice = matchingVoice;

        utterance.onstart = () => {
            if (aiStatus) {
                aiStatus.textContent = speechLanguage === "ta-IN"
                    ? "AI பேசுகிறது..."
                    : "AI is speaking...";
            }
        };

        utterance.onend = () => {
            if (aiStatus) {
                aiStatus.textContent = speechLanguage === "ta-IN"
                    ? "முடிந்தது."
                    : "Finished speaking.";
            }
        };

        utterance.onerror = () => {
            if (aiStatus) {
                aiStatus.textContent = "Could not play voice. Check browser voice settings.";
            }
        };

        window.speechSynthesis.speak(utterance);
    }

    // Send message to Flask AI
    async function sendMessage(message, speakReply = true) {
        message = String(message ?? "").trim();

        if (!message || !chatForm || !aiMessage || !sendButton) return;

        addChatMessage("user", message);
        aiMessage.value = "";
        sendButton.disabled = true;
        sendButton.textContent = "Thinking...";

        if (aiStatus) {
            aiStatus.textContent = speechLanguage === "ta-IN"
                ? "AI யோசிக்கிறது..."
                : "AI is preparing your response...";
        }

        try {
            const response = await fetch("/ask-ai", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message })
            });

            let data;

            try {
                data = await response.json();
            } catch {
                throw new Error("Invalid server response. Check the Flask terminal.");
            }

            if (!response.ok) {
                throw new Error(data.error || "Could not contact the AI.");
            }

            lastAnswer = data.reply || "I couldn't generate a response.";
            addChatMessage("assistant", lastAnswer);

            if (speakReply) {
                speakText(lastAnswer);
            } else if (aiStatus) {
                aiStatus.textContent = "AI response ready.";
            }
        } catch (error) {
            addChatMessage(
                "assistant",
                error.message || "Something went wrong. Please try again."
            );

            if (aiStatus) aiStatus.textContent = "AI request failed.";
        } finally {
            sendButton.disabled = false;
            sendButton.textContent = "Ask AI";
        }
    }

    // AI microphone
    if (aiMic && stopAiMic && aiStatus && aiMessage) {
        aiMic.addEventListener("click", () => {
            startListening(aiMessage, aiStatus, aiMic, (spokenText) => {
                aiMessage.value = spokenText;
                sendMessage(spokenText, true);
            });
        });

        stopAiMic.addEventListener("click", () => {
            stopListening(aiStatus);
        });
    }

    // Read the latest AI answer
    if (readAnswerButton) {
        readAnswerButton.addEventListener("click", () => {
            if (lastAnswer) {
                speakText(lastAnswer);
            } else if (aiStatus) {
                aiStatus.textContent = "Ask AI first to hear its answer.";
            }
        });
    }

    // AI chat form
    if (chatForm) {
        chatForm.addEventListener("submit", (event) => {
            event.preventDefault();
            sendMessage(aiMessage.value, true);
        });
    }

    // One automatic greeting only.
    // dashboard.html should have an empty #ai-chat element.
    function startGreeting() {
        if (greetingStarted || !chatBox) return;
        greetingStarted = true;

        const greeting = speechLanguage === "ta-IN"
            ? "வணக்கம்! இன்று உங்கள் நாள் எப்படி இருந்தது? இன்று நீங்கள் என்ன முயற்சி செய்தீர்கள்?"
            : "Hi! How was your day? What did you try today?";

        lastAnswer = greeting;
        addChatMessage("assistant", greeting);
        speakText(greeting);
    }

    if (chatBox) {
        window.setTimeout(startGreeting, 700);
    }

    // Clean up on page exit
    window.addEventListener("beforeunload", () => {
        if (activeRecognition) {
            try {
                activeRecognition.stop();
            } catch (error) {
                console.warn(error);
            }
        }

        if ("speechSynthesis" in window) {
            window.speechSynthesis.cancel();
        }
    });
});
