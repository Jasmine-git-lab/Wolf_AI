// ============================================================
// WOLF FRONTEND
// renderer.js
//
// Phase 3 microphone lifecycle:
//
// START LISTENING
//       ↓
// Microphone permission
//       ↓
// Wake-word recognition
//       ↓
// "Hey Wolf"
//       ↓
// Command recognition
//       ↓
// /ask
//       ↓
// Windows / Browser action OR Gemini
//       ↓
// Show USER + WOLF text
//       ↓
// Speak Wolf response
//       ↓
// STOPPED
//
// IMPORTANT:
// After one voice command completes, Wolf does NOT
// automatically return to wake-word mode.
//
// User must explicitly click "Start Listening" again.
//
// STOP LISTENING
//       ↓
// Everything stops
// ============================================================


const {
    ipcRenderer
} = require("electron");


// ============================================================
// DOM
// ============================================================

const statusText =
    document.getElementById("statusText");

const statusSubtitle =
    document.getElementById("statusSubtitle");

const voiceStatus =
    document.getElementById("voiceStatus");

const micIndicator =
    document.getElementById("micIndicator");

const chatBox =
    document.getElementById("chatBox");

const textInput =
    document.getElementById("textInput");

const sendButton =
    document.getElementById("sendButton");

const startButton =
    document.getElementById("startListening");

const stopButton =
    document.getElementById("stopListening");

const connectionStatus =
    document.getElementById("connectionStatus");

const hudCapsule =
    document.getElementById("hudCapsule");

const wolfCircle =
    document.getElementById("wolfCircle");

const pinBtn =
    document.getElementById("pinBtn");

const minBtn =
    document.getElementById("minBtn");

const closeBtn =
    document.getElementById("closeBtn");

const IDLE_AUTO_DISMISS_DELAY_MS = 3500;

const ALL_ASSISTANT_STATES = [
    "state-idle",
    "state-listening",
    "state-transcribing",
    "state-thinking",
    "state-searching",
    "state-speaking",
    "state-stopped"
];

function setAssistantVisualState(stateName) {
    if (!hudCapsule) return;
    ALL_ASSISTANT_STATES.forEach(s => hudCapsule.classList.remove(s));
    if (stateName) {
        const cls = stateName.startsWith("state-") ? stateName : `state-${stateName}`;
        hudCapsule.classList.add(cls);
    }
}


// ============================================================
// STATE
// ============================================================

let listeningEnabled = false;

let wakeRecognition = null;

let commandRecognition = null;

let commandMode = false;

let processingCommand = false;

let recognitionRestartTimer = null;

let lastCommand = "";

let activeMicStream = null;
let activeMediaRecorder = null;
let recordedAudioChunks = [];
let audioRecordingTimer = null;


// ============================================================
// SPEECH RECOGNITION
// ============================================================

const SpeechRecognition =
    window.SpeechRecognition ||
    window.webkitSpeechRecognition;


// ============================================================
// LOG
// ============================================================

function log(...args) {

    console.log(
        "[Wolf]",
        ...args
    );

}


// ============================================================
// UI STATUS
// ============================================================

function setStatus(
    title,
    subtitle,
    voice = ""
) {

    if (statusText) {

        statusText.textContent =
            title;

    }

    if (statusSubtitle) {

        statusSubtitle.textContent =
            subtitle;

    }

    if (voiceStatus) {

        voiceStatus.textContent =
            voice;

    }

    // Auto-sync Assistant HUD visual state based on status message
    const t = (title || "").toLowerCase();
    const s = (subtitle || "").toLowerCase();
    if (t.includes("speaking")) {
        setAssistantVisualState("speaking");
    } else if (t.includes("search") || s.includes("search")) {
        setAssistantVisualState("searching");
    } else if (t.includes("transcrib") || t.includes("processing")) {
        setAssistantVisualState("transcribing");
    } else if (t.includes("thinking")) {
        setAssistantVisualState("thinking");
    } else if (t.includes("listening")) {
        setAssistantVisualState("listening");
    } else if (t.includes("stopped") || t.includes("blocked") || t.includes("denied") || t.includes("error") || t.includes("unavailable")) {
        setAssistantVisualState("stopped");
    } else if (t.includes("ready")) {
        setAssistantVisualState("idle");
    }

}


// ============================================================
// MICROPHONE UI
// ============================================================

function setMicState(
    active
) {

    if (!micIndicator) {

        return;

    }


    if (active) {

        micIndicator.classList.add(
            "active"
        );

    } else {

        micIndicator.classList.remove(
            "active"
        );

    }

}


// ============================================================
// CHAT
// ============================================================

function addMessage(
    sender,
    message
) {

    if (!chatBox) {

        return;

    }

    // Modern Assistant HUD: Keep display focused only on current interaction
    if (sender === "USER") {
        chatBox.innerHTML = "";
    }


    const wrapper =
        document.createElement(
            "div"
        );


    wrapper.className =
        "message " +
        (
            sender === "USER"
                ? "user-message"
                : "wolf-message"
        );


    const label =
        document.createElement(
            "div"
        );


    label.className =
        "message-label";


    label.textContent =
        sender;


    const text =
        document.createElement(
            "div"
        );


    text.className =
        "message-text";


    text.textContent =
        message;


    wrapper.appendChild(
        label
    );


    wrapper.appendChild(
        text
    );


    chatBox.appendChild(
        wrapper
    );


    chatBox.scrollTop =
        chatBox.scrollHeight;


    return wrapper;

}


// ============================================================
// REPLACE LAST USER MESSAGE
// ============================================================

function updateUserMessage(
    message
) {

    if (!chatBox) {

        return;

    }

    // If previous Wolf response exists, user is starting a new interaction: clear old turn
    if (chatBox.querySelector(".wolf-message")) {
        chatBox.innerHTML = "";
    }


    const messages =
        chatBox.querySelectorAll(
            ".user-message"
        );


    if (!messages.length) {

        addMessage(
            "USER",
            message
        );

        return;

    }


    const last =
        messages[
            messages.length - 1
        ];


    const text =
        last.querySelector(
            ".message-text"
        );


    if (text) {

        text.textContent =
            message;

    }


    chatBox.scrollTop =
        chatBox.scrollHeight;

}


// ============================================================
// REPLACE LAST WOLF MESSAGE
// ============================================================

function updateWolfMessage(
    message
) {

    if (!chatBox) {

        return;

    }


    const messages =
        chatBox.querySelectorAll(
            ".wolf-message"
        );


    if (!messages.length) {

        addMessage(
            "WOLF",
            message
        );

        return;

    }


    const last =
        messages[
            messages.length - 1
        ];


    const text =
        last.querySelector(
            ".message-text"
        );


    if (text) {

        text.textContent =
            message;

    }


    chatBox.scrollTop =
        chatBox.scrollHeight;

}


// ============================================================
// SPEAK
// ============================================================

function speakWolf(
    text
) {

    if (
        !window.speechSynthesis
    ) {

        finishVoiceCycle();

        return;

    }


    window.speechSynthesis.cancel();


    const utterance =
        new SpeechSynthesisUtterance(
            text
        );


    utterance.rate =
        1.0;


    utterance.pitch =
        1.0;


    utterance.volume =
        1.0;


    utterance.onstart =
        () => {

            setStatus(
                "Wolf is speaking",
                "Response received",
                "Speaking"
            );

        };


    utterance.onend =
        () => {

            log(
                "Wolf speech finished."
            );
            voicePerf.tTtsEnd = Date.now();


            // IMPORTANT:
            // Do NOT restart wake recognition.
            //
            // One voice command = one listening cycle.
            // The user must click Start Listening again.

            finishVoiceCycle();

        };


    utterance.onerror =
        event => {

            log(
                "Speech synthesis error:",
                event.error
            );


            // Even if speech fails, the voice cycle
            // must still finish and remain stopped.

            finishVoiceCycle();

        };


    window.speechSynthesis.speak(
        utterance
    );

}


// ============================================================
// FINISH VOICE CYCLE
// ============================================================
//
// This is the central Phase 3 lifecycle function.
//
// It completely ends the current voice cycle.
//
// IMPORTANT:
// listeningEnabled becomes FALSE here.
//
// Therefore:
// - wake recognition cannot restart
// - command recognition cannot restart
// - speech completion cannot restart listening
//
// User must explicitly click Start Listening.
// ============================================================

function finishVoiceCycle() {

    log(
        "Finishing voice cycle."
    );

    listeningEnabled =
        false;

    commandMode =
        false;

    processingCommand =
        false;

    clearTimeout(
        recognitionRestartTimer
    );

    recognitionRestartTimer =
        null;

    stopWakeListening();

    stopCommandRecognition();

    releaseMicrophone();

    setMicState(
        false
    );

    setStatus(
        "Listening stopped",
        'Press "Start Listening" to activate Wolf',
        "Microphone off"
    );

    log(
        "Voice cycle stopped. Waiting for explicit Start Listening."
    );

    // Phase 4: Start HUD auto-dismiss countdown after completion
    ipcRenderer.send("start-auto-dismiss", { delayMs: IDLE_AUTO_DISMISS_DELAY_MS });

}


// ============================================================
// MICROPHONE HARDWARE LIFECYCLE
// ============================================================

function releaseMicrophone() {
    stopVadLoop();
    if (audioRecordingTimer) {
        clearTimeout(audioRecordingTimer);
        audioRecordingTimer = null;
    }
    if (activeMediaRecorder && activeMediaRecorder.state !== "inactive") {
        try {
            activeMediaRecorder.ondataavailable = null;
            activeMediaRecorder.onstop = null;
            activeMediaRecorder.stop();
        } catch (e) {}
    }
    activeMediaRecorder = null;
    recordedAudioChunks = [];

    if (micSourceNode) {
        try {
            micSourceNode.disconnect();
        } catch (e) {}
        micSourceNode = null;
    }
    micAnalyser = null;
    if (audioContext && audioContext.state !== "closed") {
        try {
            audioContext.close();
        } catch (e) {}
        audioContext = null;
    }

    if (activeMicStream) {
        try {
            activeMicStream.getTracks().forEach(track => track.stop());
        } catch (e) {}
        activeMicStream = null;
    }
    log("Microphone hardware and VAD audio nodes released cleanly.");
}


// ============================================================
// REQUEST MICROPHONE
// ============================================================

async function requestMicrophone() {

    try {

        if (activeMicStream && activeMicStream.active) {
            return true;
        }

        const stream =
            await navigator.mediaDevices.getUserMedia(
                {
                    audio: true,
                    video: false
                }
            );

        log(
            "Microphone permission granted."
        );

        activeMicStream = stream;
        return true;

    } catch (error) {

        console.error(
            "Microphone permission failed:",
            error
        );

        setStatus(
            "Microphone blocked",
            "Allow microphone access and try again",
            "Microphone unavailable"
        );

        addMessage(
            "WOLF",
            "I cannot access the microphone. Please allow microphone permission for Wolf."
        );

        return false;

    }

}


// ============================================================
// VOICE ACTIVITY DETECTION (VAD) & HYBRID AUDIO RECORDING
// ============================================================

let audioContext = null;
let micAnalyser = null;
let micSourceNode = null;
let vadTimer = null;
let vadActive = false;
let vadUserSpoke = false;
let vadLastSpeechTimestamp = 0;
let vadSilenceStartTimestamp = 0;

let currentUtteranceProcessed = false;
let currentCapturedText = "";

const VAD_SPEECH_THRESHOLD = 0.024;      // RMS energy threshold for active speech
const VAD_NATURAL_PAUSE_MS = 1400;       // Natural human pause window (breaths, thinking, clause gaps)
const VAD_MAX_INITIAL_SILENCE_MS = 7500; // Time to start speaking before prompt timeout

// Lightweight performance timing tracker
const voicePerf = {
    tActivation: 0,
    tFirstAudio: 0,
    tSpeechStart: 0,
    tSpeechEnd: 0,
    tTranscribeStart: 0,
    tTranscribeComplete: 0,
    tCommandSubmit: 0,
    tProcessStart: 0,
    tResponseReceived: 0,
    tTtsStart: 0,
    tTtsEnd: 0,
    reset() {
        this.tActivation = Date.now();
        this.tFirstAudio = 0;
        this.tSpeechStart = 0;
        this.tSpeechEnd = 0;
        this.tTranscribeStart = 0;
        this.tTranscribeComplete = 0;
        this.tCommandSubmit = 0;
        this.tProcessStart = 0;
        this.tResponseReceived = 0;
        this.tTtsStart = 0;
        this.tTtsEnd = 0;
    },
    logSummary() {
        const speechDur = (this.tSpeechEnd && this.tSpeechStart) ? (this.tSpeechEnd - this.tSpeechStart) : 0;
        const transcribeLatency = (this.tTranscribeComplete && this.tSpeechEnd) ? (this.tTranscribeComplete - this.tSpeechEnd) : 0;
        const backendLatency = (this.tResponseReceived && this.tCommandSubmit) ? (this.tResponseReceived - this.tCommandSubmit) : 0;
        const ttsStartLatency = (this.tTtsStart && this.tResponseReceived) ? (this.tTtsStart - this.tResponseReceived) : 0;
        const totalDuration = (this.tTtsStart && this.tActivation) ? (this.tTtsStart - this.tActivation) : 0;

        log(
            `[Voice Perf] Total Voice-to-TTS: ${totalDuration}ms | ` +
            `Speech: ${speechDur}ms | ` +
            `Transcription: ${transcribeLatency}ms | ` +
            `Backend /ask: ${backendLatency}ms | ` +
            `TTS delay: ${ttsStartLatency}ms`
        );
    }
};

function initAudioAnalyser() {
    try {
        if (!activeMicStream) return;
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (!AudioCtx) return;

        if (!audioContext || audioContext.state === "closed") {
            audioContext = new AudioCtx();
        }
        if (audioContext && audioContext.state === "suspended") {
            audioContext.resume().catch(() => {});
        }
        if (audioContext && !micAnalyser) {
            micAnalyser = audioContext.createAnalyser();
            micAnalyser.fftSize = 512;
            micAnalyser.smoothingTimeConstant = 0.3;
            micSourceNode = audioContext.createMediaStreamSource(activeMicStream);
            micSourceNode.connect(micAnalyser);
            log("VAD AudioAnalyser connected to active mic stream.");
        }
    } catch (err) {
        log("initAudioAnalyser error:", err);
    }
}

function getAudioEnergy() {
    if (!micAnalyser) return 0;
    const data = new Uint8Array(micAnalyser.fftSize);
    micAnalyser.getByteTimeDomainData(data);
    let sum = 0;
    for (let i = 0; i < data.length; i++) {
        const normalized = (data[i] - 128) / 128;
        sum += normalized * normalized;
    }
    return Math.sqrt(sum / data.length);
}

function stopVadLoop() {
    vadActive = false;
    if (vadTimer) {
        clearInterval(vadTimer);
        vadTimer = null;
    }
}

function startVadLoop(onEndOfSpeech) {
    stopVadLoop();
    const vadStartTime = Date.now();
    vadActive = true;
    vadUserSpoke = false;
    vadLastSpeechTimestamp = 0;
    vadSilenceStartTimestamp = 0;

    vadTimer = setInterval(() => {
        if (!vadActive || !listeningEnabled || !commandMode || processingCommand) {
            stopVadLoop();
            return;
        }

        const energy = getAudioEnergy();
        const now = Date.now();

        // 1. Audio Energy above threshold -> ACTIVE SPEECH DETECTED
        if (energy >= VAD_SPEECH_THRESHOLD) {
            if (!voicePerf.tFirstAudio) {
                voicePerf.tFirstAudio = now;
            }
            if (!vadUserSpoke) {
                vadUserSpoke = true;
                voicePerf.tSpeechStart = now;
                log("VAD: Active speech started (energy: " + energy.toFixed(4) + ")");
            }
            vadLastSpeechTimestamp = now;
            vadSilenceStartTimestamp = 0;

            // Keep assistant in LISTENING state while user is actively talking
            if (hudCapsule && !hudCapsule.classList.contains("state-listening")) {
                setAssistantVisualState("listening");
            }
        }
        // 2. Audio Energy below threshold -> PAUSE OR SILENCE
        else {
            if (vadUserSpoke) {
                // User has spoken earlier, now experiencing a pause
                if (vadSilenceStartTimestamp === 0) {
                    vadSilenceStartTimestamp = now;
                }
                const pauseDuration = now - vadSilenceStartTimestamp;

                // Stop listening ONLY when silence exceeds natural human speech pause window
                if (pauseDuration >= VAD_NATURAL_PAUSE_MS) {
                    log(`VAD: Genuine end of speech detected after ${pauseDuration}ms silence.`);
                    stopVadLoop();
                    voicePerf.tSpeechEnd = vadLastSpeechTimestamp || now;
                    if (onEndOfSpeech) {
                        onEndOfSpeech();
                    }
                }
            } else {
                // User has not started speaking yet
                if (now - vadStartTime >= VAD_MAX_INITIAL_SILENCE_MS) {
                    log("VAD: Max initial silence timeout reached without speech.");
                    stopVadLoop();
                    handleNoSpeechDetected();
                }
            }
        }
    }, 50);
}

function startAudioRecording() {
    try {
        recordedAudioChunks = [];
        if (!activeMicStream || !activeMicStream.active) {
            navigator.mediaDevices.getUserMedia({ audio: true, video: false })
                .then(stream => {
                    activeMicStream = stream;
                    initMediaRecorder();
                })
                .catch(err => log("Could not re-acquire mic stream:", err));
            return;
        }
        initMediaRecorder();
    } catch (err) {
        log("startAudioRecording error:", err);
    }
}

function initMediaRecorder() {
    if (!activeMicStream) return;
    try {
        let mimeType = "audio/webm";
        if (typeof MediaRecorder !== "undefined") {
            if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) {
                mimeType = "audio/webm;codecs=opus";
            } else if (MediaRecorder.isTypeSupported("audio/webm")) {
                mimeType = "audio/webm";
            }
            activeMediaRecorder = new MediaRecorder(activeMicStream, { mimeType });
            activeMediaRecorder.ondataavailable = (event) => {
                if (event.data && event.data.size > 0) {
                    recordedAudioChunks.push(event.data);
                }
            };
            activeMediaRecorder.start(200);
            log("MediaRecorder active. MimeType:", mimeType);
        }
    } catch (err) {
        log("initMediaRecorder error:", err);
    }
}

async function stopAudioRecordingAndTranscribe() {
    if (audioRecordingTimer) {
        clearTimeout(audioRecordingTimer);
        audioRecordingTimer = null;
    }
    if (!activeMediaRecorder || activeMediaRecorder.state === "inactive") {
        return null;
    }

    return new Promise((resolve) => {
        activeMediaRecorder.onstop = async () => {
            try {
                const blob = new Blob(recordedAudioChunks, {
                    type: (activeMediaRecorder && activeMediaRecorder.mimeType) || "audio/webm"
                });
                recordedAudioChunks = [];
                log("Recorded audio blob size:", blob.size);

                if (blob.size < 500) {
                    resolve(null);
                    return;
                }

                setStatus(
                    "Processing",
                    "Transcribing audio...",
                    "Working..."
                );

                const formData = new FormData();
                formData.append("audio", blob, "command.webm");

                const response = await fetch("http://127.0.0.1:5000/transcribe-audio", {
                    method: "POST",
                    body: formData,
                });

                const data = await response.json();
                if (data.ok && data.text && data.text.trim()) {
                    log("Transcribe audio returned:", data.text);
                    resolve(data.text.trim());
                    return;
                }
            } catch (err) {
                log("stopAudioRecordingAndTranscribe error:", err);
            }
            resolve(null);
        };

        try {
            activeMediaRecorder.stop();
        } catch (e) {
            resolve(null);
        }
    });
}


// ============================================================
// CREATE WAKE RECOGNIZER
// ============================================================

function createWakeRecognition() {

    if (!SpeechRecognition) {

        addMessage(
            "WOLF",
            "Speech recognition is not available in this Electron environment."
        );


        return null;

    }


    const recognition =
        new SpeechRecognition();


    recognition.continuous =
        true;


    recognition.interimResults =
        true;


    recognition.lang =
        "en-US";


    recognition.maxAlternatives =
        3;


    recognition.onstart =
        () => {

            log(
                "Wake recognition started."
            );


            setMicState(
                true
            );


            setStatus(
                "Listening",
                'Say "Hey Wolf"',
                "Waiting for wake word"
            );

        };


    recognition.onresult =
        event => {

            for (
                let i = event.resultIndex;
                i < event.results.length;
                i++
            ) {

                const result =
                    event.results[i];


                const transcript =
                    result[0]
                        .transcript
                        .trim();


                log(
                    "Wake transcript:",
                    transcript
                );


                if (
                    isWakeWord(
                        transcript
                    )
                ) {

                    log(
                        "WAKE WORD DETECTED"
                    );


                    activateCommandMode();


                    return;

                }

            }

        };


    recognition.onerror =
        event => {

            log(
                "Wake recognition error:",
                event.error
            );


            if (
                event.error ===
                "not-allowed"
            ) {

                listeningEnabled =
                    false;


                setMicState(
                    false
                );


                setStatus(
                    "Microphone permission denied",
                    "Allow microphone access",
                    "Stopped"
                );


                return;

            }


            if (
                event.error ===
                "audio-capture"
            ) {

                setStatus(
                    "Microphone unavailable",
                    "Check Windows microphone settings",
                    "Microphone error"
                );

            }

        };


    recognition.onend =
        () => {

            log(
                "Wake recognition ended."
            );


            // Controlled restart ONLY while the user
            // has explicitly enabled listening and no
            // command is being processed.

            if (
                listeningEnabled &&
                !commandMode &&
                !processingCommand
            ) {

                clearTimeout(
                    recognitionRestartTimer
                );


                recognitionRestartTimer =
                    setTimeout(
                        () => {

                            if (
                                listeningEnabled &&
                                !commandMode &&
                                !processingCommand
                            ) {

                                startWakeListening();

                            }

                        },
                        300
                    );

            }

        };


    return recognition;

}


// ============================================================
// CREATE COMMAND RECOGNIZER
// ============================================================

function createCommandRecognition() {

    if (!SpeechRecognition) {

        return null;

    }


    const recognition =
        new SpeechRecognition();

    // Continuous mode prevents premature cutoff on natural pauses between clauses
    recognition.continuous =
        true;

    recognition.interimResults =
        true;

    recognition.lang =
        "en-US";

    recognition.maxAlternatives =
        3;

    recognition.onstart =
        () => {

            log(
                "Command recognition started (continuous mode)."
            );

            setMicState(
                true
            );

            setStatus(
                "Listening for command",
                "Speak now",
                "Command mode"
            );

        };

    recognition.onresult =
        event => {

            let accumulatedFinal =
                "";

            let interimText =
                "";

            for (
                let i = 0;
                i < event.results.length;
                i++
            ) {

                const res =
                    event.results[i];

                const transcript =
                    res[0]
                        .transcript
                        .trim();

                if (
                    res.isFinal
                ) {

                    accumulatedFinal +=
                        transcript + " ";

                } else {

                    interimText +=
                        transcript + " ";

                }

            }

            const fullLiveText =
                (
                    accumulatedFinal +
                    interimText
                ).trim();

            if (
                fullLiveText
            ) {

                currentCapturedText =
                    fullLiveText;

                updateUserMessage(
                    fullLiveText
                );

                // Words arriving confirm speech activity and reset silence timer
                vadUserSpoke =
                    true;

                vadLastSpeechTimestamp =
                    Date.now();

                vadSilenceStartTimestamp =
                    0;

                if (!voicePerf.tSpeechStart) {

                    voicePerf.tSpeechStart =
                        Date.now();

                }

            }

            // Partial Transcription Protection:
            // Do NOT trigger command execution on interim or partial results.
            // Execution is strictly triggered upon verified end-of-speech.

        };

    recognition.onerror =
        event => {

            log(
                "Command recognition error:",
                event.error
            );

            if (
                currentUtteranceProcessed ||
                processingCommand
            ) {

                return;

            }

            if (
                event.error ===
                "aborted"
            ) {

                return;

            }

            if (
                event.error ===
                "network"
            ) {

                // Web Speech API network restricted in Electron.
                // Parallel MediaRecorder with VAD automatically handles transcription.
                log(
                    "Web Speech API network restricted. Parallel MediaRecorder with VAD is active."
                );

                return;

            }

            if (
                event.error ===
                "no-speech"
            ) {

                // Ignore transient no-speech if user spoke or VAD is monitoring
                if (
                    vadUserSpoke ||
                    (currentCapturedText && currentCapturedText.trim())
                ) {

                    log(
                        "Transient no-speech ignored; speech already detected by VAD."
                    );

                    return;

                }

                return;

            }

            if (
                event.error ===
                "not-allowed"
            ) {

                currentUtteranceProcessed =
                    true;

                stopVadLoop();

                addMessage(
                    "WOLF",
                    "Microphone access was denied. Please allow microphone permissions."
                );

                setStatus(
                    "Microphone permission denied",
                    "Allow microphone access and press Start Listening",
                    "Microphone off"
                );

                finishVoiceCycle();

                return;

            }

        };

    recognition.onend =
        () => {

            log(
                "Command recognition session ended. Captured text:",
                currentCapturedText
            );

            // If recognition engine ended naturally and speech was captured, finalize
            if (
                !currentUtteranceProcessed &&
                !processingCommand &&
                listeningEnabled &&
                commandMode
            ) {

                if (
                    currentCapturedText &&
                    currentCapturedText.trim()
                ) {

                    finalizeSpeechAndExecute();

                }

            }

        };

    return recognition;

}


// ============================================================
// UTTERANCE FINALIZATION & EXECUTION
// ============================================================

async function finalizeSpeechAndExecute() {

    if (
        currentUtteranceProcessed ||
        processingCommand
    ) {

        return;

    }

    currentUtteranceProcessed =
        true;

    stopVadLoop();

    // Visual state transition: LISTENING -> TRANSCRIBING
    setStatus(
        "Transcribing",
        currentCapturedText || "Transcribing speech...",
        "Transcribing"
    );

    if (
        commandRecognition
    ) {

        try {

            commandRecognition.stop();

        } catch (e) {}

    }

    voicePerf.tTranscribeStart =
        Date.now();

    // Primary: text captured by Web Speech API
    if (
        currentCapturedText &&
        currentCapturedText.trim()
    ) {

        const textToRun =
            currentCapturedText.trim();

        log(
            "Utterance finalized via Web Speech API:",
            textToRun
        );

        voicePerf.tTranscribeComplete =
            Date.now();

        voicePerf.tCommandSubmit =
            Date.now();

        await processVoiceCommand(
            textToRun
        );

        return;

    }

    // Fallback: Gemini multimodal audio transcription of MediaRecorder buffer
    log(
        "Web Speech transcript empty. Transcribing audio buffer via backend..."
    );

    const audioText =
        await stopAudioRecordingAndTranscribe();

    if (
        audioText &&
        audioText.trim()
    ) {

        log(
            "Utterance finalized via Gemini Audio fallback:",
            audioText.trim()
        );

        voicePerf.tTranscribeComplete =
            Date.now();

        updateUserMessage(
            audioText.trim()
        );

        voicePerf.tCommandSubmit =
            Date.now();

        await processVoiceCommand(
            audioText.trim()
        );

    } else {

        log(
            "No discernible speech transcribed from audio buffer."
        );

        addMessage(
            "WOLF",
            "I did not detect any speech, Sir. Please try again."
        );

        setStatus(
            "Listening stopped",
            'Press "Start Listening" to try again',
            "Microphone off"
        );

        finishVoiceCycle();

    }

}

function handleNoSpeechDetected() {

    if (
        currentUtteranceProcessed ||
        processingCommand
    ) {

        return;

    }

    currentUtteranceProcessed =
        true;

    stopVadLoop();

    stopCommandRecognition();

    addMessage(
        "WOLF",
        "I did not detect any speech, Sir. Please try again."
    );

    setStatus(
        "Listening stopped",
        'Press "Start Listening" to try again',
        "Microphone off"
    );

    finishVoiceCycle();

}


// ============================================================
// WAKE WORD
// ============================================================

function isWakeWord(
    text
) {

    const value =
        text
            .toLowerCase()
            .replace(
                /[.,!?]/g,
                " "
            )
            .replace(
                /\s+/g,
                " "
            )
            .trim();


    const patterns = [

        "hey wolf",

        "hey woolf",

        "hey woof",

        "hey wulf",

        "a wolf",

    ];


    return patterns.some(
        pattern =>
            value.includes(
                pattern
            )
    );

}


// ============================================================
// EXTRACT COMMAND AFTER WAKE WORD
// ============================================================

function removeWakeWord(
    text
) {

    return text
        .replace(
            /^\s*hey\s+wolf[\s,.:;-]*/i,
            ""
        )
        .trim();

}


// ============================================================
// ACTIVATE COMMAND MODE
// ============================================================

function activateCommandMode() {

    if (
        !listeningEnabled ||
        processingCommand
    ) {

        return;

    }


    commandMode =
        true;


    stopWakeListening();


    setStatus(
        "Listening for command",
        "Speak now",
        "Command mode"
    );

    currentUtteranceProcessed =
        false;

    currentCapturedText =
        "";

    voicePerf.reset();

    // Start audio capture & VAD immediately (0 artificial startup delay)
    initAudioAnalyser();
    startAudioRecording();

    commandRecognition =
        createCommandRecognition();

    if (
        commandRecognition
    ) {

        try {

            commandRecognition.start();

        } catch (error) {

            log(
                "Command recognition start exception:",
                error
            );

        }

    }

    // Start real-time VAD loop to monitor speech energy and detect end of utterance
    startVadLoop(finalizeSpeechAndExecute);

}


// ============================================================
// PROCESS VOICE COMMAND
// ============================================================

async function processVoiceCommand(
    text
) {

    if (
        processingCommand
    ) {

        return;

    }


    processingCommand =
        true;

    voicePerf.tProcessStart =
        Date.now();


    let command =
        removeWakeWord(
            text
        );


    if (!command) {

        command =
            text;

    }


    lastCommand =
        command;


    updateUserMessage(
        command
    );


    const cmdLower =
        command.toLowerCase();

    const isSearch =
        cmdLower.includes("search") ||
        cmdLower.includes("google") ||
        cmdLower.includes("youtube");

    setStatus(
        isSearch
            ? "Searching"
            : "Thinking",
        command,
        "Working..."
    );


    stopCommandRecognition();


    try {

        const response =
            await fetch(
                "http://127.0.0.1:5000/ask",
                {

                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({
                        message: command
                    })

                }
            );


        voicePerf.tResponseReceived =
            Date.now();


        const data =
            await response.json();


        if (
            !response.ok ||
            !data.ok
        ) {

            throw new Error(
                data.error ||
                "Request failed."
            );

        }


        const answer =
            data.message ||
            "Done, Sir.";


        addMessage(
            "WOLF",
            answer
        );


        voicePerf.tTtsStart =
            Date.now();

        voicePerf.logSummary();


        speakWolf(
            answer
        );


    } catch (error) {

        console.error(
            "Voice command error:",
            error
        );


        const message =
            "Sorry, Sir. I could not process that request. "
            + "(" + (error.message || "Network error") + ")";


        addMessage(
            "WOLF",
            message
        );


        speakWolf(
            "Sorry, Sir. I could not process that request."
        );

    } finally {

        processingCommand =
            false;


        commandMode =
            false;

    }

}


// ============================================================
// START WAKE LISTENING
// ============================================================

async function startWakeListening() {

    if (
        !listeningEnabled
    ) {

        return;

    }


    if (
        commandMode ||
        processingCommand
    ) {

        return;

    }


    if (
        !SpeechRecognition
    ) {

        setStatus(
            "Speech recognition unavailable",
            "Use the text box",
            "Unavailable"
        );


        return;

    }


    if (
        !wakeRecognition
    ) {

        wakeRecognition =
            createWakeRecognition();

    }


    if (
        !wakeRecognition
    ) {

        return;

    }


    try {

        wakeRecognition.start();

    } catch (error) {

        // Browser throws InvalidStateError
        // if already running.

        log(
            "Wake start ignored:",
            error.message
        );

    }

}


// ============================================================
// STOP WAKE LISTENING
// ============================================================

function stopWakeListening() {

    if (
        !wakeRecognition
    ) {

        return;

    }


    try {

        wakeRecognition.stop();

    } catch (error) {

        log(
            "Wake stop:",
            error.message
        );

    }

    // *** BUG FIX: Always null-out after stopping.
    // Reusing a stopped SpeechRecognition object in Electron's
    // Chromium throws InvalidStateError silently and recognition
    // never restarts. startWakeListening() will create a fresh one.
    wakeRecognition = null;

}


// ============================================================
// STOP COMMAND
// ============================================================

function stopCommandRecognition() {

    stopVadLoop();

    if (
        !commandRecognition
    ) {

        return;

    }


    try {

        commandRecognition.stop();

    } catch (error) {

        log(
            "Command stop:",
            error.message
        );

    }


    commandRecognition =
        null;

}


// ============================================================
// START LISTENING BUTTON
// ============================================================

async function startListening() {

    if (
        listeningEnabled
    ) {

        return;

    }


    const microphoneOK =
        await requestMicrophone();


    if (
        !microphoneOK
    ) {

        return;

    }


    listeningEnabled =
        true;


    commandMode =
        false;


    processingCommand =
        false;


    clearTimeout(
        recognitionRestartTimer
    );


    recognitionRestartTimer =
        null;


    // *** BUG FIX: Go directly to command recognition.
    // Previously this started wake-word listening, which required
    // the user to say "Hey Wolf" before their actual command was
    // captured. That second stage often failed silently because
    // the wake recognizer was never nulled on stop (now fixed too).
    //
    // New behavior: pressing Start Listening immediately opens a
    // command recognition window. After the command completes
    // or times out, listeningEnabled returns to false and the
    // user presses the button again for the next command.

    setStatus(
        "Listening",
        "Speak your command now",
        "Command mode active"
    );


    addMessage(
        "WOLF",
        "Listening. Speak your command now, Sir."
    );


    activateCommandMode();

}


// ============================================================
// STOP LISTENING BUTTON
// ============================================================

function stopListening() {

    listeningEnabled =
        false;


    commandMode =
        false;


    processingCommand =
        false;

    currentUtteranceProcessed =
        true;

    stopVadLoop();


    clearTimeout(
        recognitionRestartTimer
    );


    recognitionRestartTimer =
        null;


    stopWakeListening();

    stopCommandRecognition();

    releaseMicrophone();


    if (
        window.speechSynthesis
    ) {

        window.speechSynthesis.cancel();

    }


    setMicState(
        false
    );


    setStatus(
        "Listening stopped",
        'Press "Start Listening" to activate Wolf',
        "Microphone off"
    );


    addMessage(
        "WOLF",
        "Listening has been stopped."
    );

}


// ============================================================
// SEND TEXT
// ============================================================

async function sendText() {

    const message =
        textInput.value.trim();


    if (!message) {

        return;

    }


    textInput.value =
        "";


    addMessage(
        "USER",
        message
    );


    setStatus(
        "Thinking",
        message,
        "Processing"
    );


    try {

        const response =
            await fetch(
                "http://127.0.0.1:5000/ask",
                {

                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({
                        message
                    })

                }
            );


        const data =
            await response.json();


        if (
            !response.ok ||
            !data.ok
        ) {

            throw new Error(
                data.error ||
                "Request failed."
            );

        }


        const answer =
            data.message ||
            "Done, Sir.";


        addMessage(
            "WOLF",
            answer
        );


        speakWolf(
            answer
        );


    } catch (error) {

        console.error(
            "Text request error:",
            error
        );


        addMessage(
            "WOLF",
            "Sorry, Sir. I could not connect to the backend."
        );


        setStatus(
            "Backend error",
            "Check Python backend",
            "Error"
        );

    }

}


// ============================================================
// BUTTON EVENTS
// ============================================================

if (startButton) {

    startButton.addEventListener(
        "click",
        startListening
    );

}


if (stopButton) {

    stopButton.addEventListener(
        "click",
        stopListening
    );

}


if (sendButton) {

    sendButton.addEventListener(
        "click",
        sendText
    );

}


if (wolfCircle) {
    const handleCircleActivate = () => {
        if (listeningEnabled) {
            stopListening();
        } else {
            startListening();
        }
    };
    wolfCircle.addEventListener("click", handleCircleActivate);
    wolfCircle.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            handleCircleActivate();
        }
    });
}


if (textInput) {

    textInput.addEventListener(
        "keydown",
        event => {

            if (
                event.key ===
                "Enter"
            ) {

                sendText();

            }

        }
    );

}


// ============================================================
// FRONTEND READY & IPC LISTENERS
// ============================================================

function showOverlay() {
    if (hudCapsule) {
        hudCapsule.classList.remove("leaving");
        hudCapsule.classList.add("entering");
    }
    ipcRenderer.send("cancel-auto-dismiss");
}

function dismissOverlay() {
    if (hudCapsule) {
        hudCapsule.classList.remove("entering");
        hudCapsule.classList.add("leaving");
        setTimeout(() => {
            ipcRenderer.send("overlay-animation-finished");
        }, 300);
    } else {
        ipcRenderer.send("hide-window");
    }
}

if (pinBtn) {
    pinBtn.addEventListener("click", () => {
        ipcRenderer.send("toggle-pin");
    });
}

if (minBtn) {
    minBtn.addEventListener("click", () => {
        ipcRenderer.send("minimize-window");
    });
}

if (closeBtn) {
    closeBtn.addEventListener("click", () => {
        dismissOverlay();
    });
}

if (hudCapsule) {
    hudCapsule.addEventListener("mouseenter", () => {
        ipcRenderer.send("cancel-auto-dismiss");
    });

    hudCapsule.addEventListener("mouseleave", () => {
        if (!listeningEnabled && !processingCommand && document.activeElement !== textInput) {
            ipcRenderer.send("start-auto-dismiss", { delayMs: IDLE_AUTO_DISMISS_DELAY_MS });
        }
    });
}

if (textInput) {
    textInput.addEventListener("focus", () => {
        ipcRenderer.send("cancel-auto-dismiss");
    });
}

ipcRenderer.send(
    "frontend-ready"
);

ipcRenderer.on("wake-wolf", () => {
    log("Received wake-wolf IPC event from Main process");
    showOverlay();
    if (!listeningEnabled) {
        startListening().catch(err => log("Wake startListening error:", err));
    }
    if (textInput) {
        textInput.focus();
    }
});

ipcRenderer.on("trigger-show-animation", () => {
    showOverlay();
});

ipcRenderer.on("trigger-dismiss-animation", () => {
    if (document.activeElement !== textInput && !listeningEnabled && !processingCommand) {
        dismissOverlay();
    } else {
        ipcRenderer.send("cancel-auto-dismiss");
    }
});

ipcRenderer.on("pin-status-changed", (event, isPinned) => {
    if (pinBtn) {
        pinBtn.classList.toggle("active", isPinned);
    }
});

ipcRenderer.on("backend-status", (event, data) => {
    log("Received backend-status IPC event:", data);
    if (!connectionStatus) return;

    if (data.status === "running") {
        connectionStatus.textContent = "Backend Connected";
        connectionStatus.className = "connection connected";
    } else if (data.status === "starting") {
        connectionStatus.textContent = "Backend Starting...";
        connectionStatus.className = "connection";
    } else if (data.status === "error") {
        connectionStatus.textContent = "Backend Error";
        connectionStatus.className = "connection error";
    } else {
        connectionStatus.textContent = "Backend Offline";
        connectionStatus.className = "connection";
    }
});

// ============================================================
// HEALTH CHECK
// ============================================================

async function checkBackend() {

    try {

        const response =
            await fetch(
                "http://127.0.0.1:5000/health"
            );


        const data =
            await response.json();


        if (
            data.ok
        ) {

            connectionStatus.textContent =
                "Backend Connected";


            connectionStatus.className =
                "connection connected";


            log(
                "Backend health:",
                data
            );

        }

    } catch (error) {

        if (connectionStatus && connectionStatus.textContent !== "Backend Starting...") {
            connectionStatus.textContent =
                "Backend Connecting...";

            connectionStatus.className =
                "connection";
        }

    }

}


setInterval(
    checkBackend,
    3000
);


checkBackend();


// ============================================================
// INITIAL UI
// ============================================================

setStatus(
    "Wolf is ready",
    'Press "Start Listening" to activate Wolf',
    "Microphone off"
);

