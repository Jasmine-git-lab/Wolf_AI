// ============================================================
// WOLF AI - ELECTRON RENDERER
// renderer.js
// ============================================================

const {
    ipcRenderer
} = require("electron");


// ============================================================
// LIVEKIT
// ============================================================

let livekit = null;
let room = null;

let livekitConnected = false;
let microphoneEnabled = false;


// ============================================================
// STATE
// ============================================================

let backendReady = false;
let isSending = false;


// ============================================================
// DOM
// ============================================================

const chatBox =
    document.getElementById("chatBox");

const userInput =
    document.getElementById("userInput");

const sendButton =
    document.getElementById("sendButton");

const statusText =
    document.getElementById("status");

const statusDot =
    document.getElementById("statusDot");

const assistantStatus =
    document.getElementById("assistantStatus");

const assistantSubtitle =
    document.getElementById("assistantSubtitle");

const wolfCircle =
    document.getElementById("wolfCircle");

const voiceStatus =
    document.getElementById("voiceStatus");


// ============================================================
// START
// ============================================================

window.addEventListener(
    "DOMContentLoaded",
    async () => {

        console.log(
            "🐺 Wolf renderer starting..."
        );

        setupTextInput();

        checkBackendHealth();

    }
);


// ============================================================
// TEXT INPUT
// ============================================================

function setupTextInput() {

    if (userInput) {

        userInput.addEventListener(
            "keydown",
            (event) => {

                if (
                    event.key === "Enter"
                ) {

                    event.preventDefault();

                    sendMessage();

                }

            }
        );

    }


    if (sendButton) {

        sendButton.addEventListener(
            "click",
            sendMessage
        );

    }

}


// ============================================================
// BACKEND HEALTH
// ============================================================

async function checkBackendHealth() {

    try {

        const response =
            await fetch(
                "http://127.0.0.1:5000/health"
            );

        if (!response.ok) {

            throw new Error(
                "Backend HTTP " +
                response.status
            );

        }

        const data =
            await response.json();

        console.log(
            "Backend health:",
            data
        );


        if (
            data.ai_ready
        ) {

            backendReady = true;

            setReadyState();


            // ------------------------------------------------
            // CONNECT LIVEKIT
            // ------------------------------------------------

            if (
                data.livekit
            ) {

                await connectLiveKit();

            }

            else {

                setVoiceStatus(
                    "🎤 LiveKit credentials unavailable"
                );

            }

        }

        else {

            backendReady = false;

            setStartingState();

            setTimeout(
                checkBackendHealth,
                1500
            );

        }

    }

    catch (error) {

        console.log(
            "Waiting for backend...",
            error
        );

        backendReady = false;

        setConnectingState();

        setTimeout(
            checkBackendHealth,
            1500
        );

    }

}


// ============================================================
// UI - CONNECTING
// ============================================================

function setConnectingState() {

    if (statusText) {

        statusText.textContent =
            "Connecting...";

    }

    if (statusDot) {

        statusDot.className =
            "status-dot connecting";

    }

    if (assistantStatus) {

        assistantStatus.textContent =
            "Connecting to Wolf...";

    }

    if (assistantSubtitle) {

        assistantSubtitle.textContent =
            "Starting the Python backend.";

    }

    if (wolfCircle) {

        wolfCircle.classList.remove(
            "ready"
        );

        wolfCircle.classList.add(
            "loading"
        );

    }

    setVoiceStatus(
        "🎤 Connecting..."
    );

}


// ============================================================
// UI - STARTING
// ============================================================

function setStartingState() {

    if (statusText) {

        statusText.textContent =
            "Initializing...";

    }

    if (statusDot) {

        statusDot.className =
            "status-dot connecting";

    }

    if (assistantStatus) {

        assistantStatus.textContent =
            "Wolf is waking up...";

    }

    if (assistantSubtitle) {

        assistantSubtitle.textContent =
            "Connecting to Gemini.";

    }

    if (wolfCircle) {

        wolfCircle.classList.remove(
            "ready"
        );

        wolfCircle.classList.add(
            "loading"
        );

    }

}


// ============================================================
// UI - READY
// ============================================================

function setReadyState() {

    if (statusText) {

        statusText.textContent =
            "Ready";

    }

    if (statusDot) {

        statusDot.className =
            "status-dot ready";

    }

    if (assistantStatus) {

        assistantStatus.textContent =
            "Wolf is ready";

    }

    if (assistantSubtitle) {

        assistantSubtitle.textContent =
            "Microphone and AI are ready.";

    }

    if (wolfCircle) {

        wolfCircle.classList.remove(
            "loading"
        );

        wolfCircle.classList.add(
            "ready"
        );

    }

}


// ============================================================
// LIVEKIT CONNECT
// ============================================================

async function connectLiveKit() {

    if (
        livekitConnected
    ) {

        return;

    }


    try {

        console.log(
            "Connecting to LiveKit..."
        );


        // ----------------------------------------------------
        // LOAD LIVEKIT CLIENT
        // ----------------------------------------------------

        livekit =
            require(
                "livekit-client"
            );


        // ----------------------------------------------------
        // GET TOKEN
        // ----------------------------------------------------

        const response =
            await fetch(
                "http://127.0.0.1:5000/livekit-token"
            );


        if (!response.ok) {

            throw new Error(
                "Token server returned " +
                response.status
            );

        }


        const data =
            await response.json();


        if (
            data.error
        ) {

            throw new Error(
                data.error
            );

        }


        if (
            !data.token
        ) {

            throw new Error(
                "No LiveKit token received."
            );

        }


        if (
            !data.url
        ) {

            throw new Error(
                "No LiveKit URL received."
            );

        }


        console.log(
            "LiveKit token received."
        );


        // ----------------------------------------------------
        // CREATE ROOM
        // ----------------------------------------------------

        room =
            new livekit.Room({

                adaptiveStream:
                    true,

                dynacast:
                    true

            });


        // ----------------------------------------------------
        // ROOM EVENTS
        // ----------------------------------------------------

        room.on(
            livekit.RoomEvent.Connected,
            () => {

                console.log(
                    "🐺 LiveKit room connected:",
                    room.name
                );

                livekitConnected =
                    true;

                setVoiceStatus(
                    "🎤 LiveKit connected"
                );

            }
        );


        room.on(
            livekit.RoomEvent.Disconnected,
            (reason) => {

                console.log(
                    "LiveKit disconnected:",
                    reason
                );

                livekitConnected =
                    false;

                microphoneEnabled =
                    false;

                setVoiceStatus(
                    "🎤 LiveKit disconnected"
                );

            }
        );


        room.on(
            livekit.RoomEvent.Reconnecting,
            () => {

                console.log(
                    "LiveKit reconnecting..."
                );

                setVoiceStatus(
                    "🎤 Reconnecting..."
                );

            }
        );


        room.on(
            livekit.RoomEvent.Reconnected,
            () => {

                console.log(
                    "LiveKit reconnected."
                );

                setVoiceStatus(
                    "🎤 Microphone connected"
                );

            }
        );


        // ----------------------------------------------------
        // REMOTE AUDIO
        // ----------------------------------------------------

        room.on(
            livekit.RoomEvent.TrackSubscribed,
            (
                track,
                publication,
                participant
            ) => {

                console.log(
                    "Remote track subscribed:",
                    track.kind,
                    participant.identity
                );


                if (
                    track.kind ===
                    livekit.Track.Kind.Audio
                ) {

                    const element =
                        track.attach();

                    element.autoplay =
                        true;

                    element.setAttribute(
                        "playsinline",
                        ""
                    );

                    document.body.appendChild(
                        element
                    );

                    element.play()
                        .catch(
                            error => {

                                console.log(
                                    "Audio play waiting:",
                                    error
                                );

                            }
                        );

                }

            }
        );


        // ----------------------------------------------------
        // CONNECT
        // ----------------------------------------------------

        await room.connect(
            data.url,
            data.token
        );


        console.log(
            "Connected to LiveKit room:",
            room.name
        );


        livekitConnected =
            true;


        // ----------------------------------------------------
        // ENABLE MICROPHONE
        // ----------------------------------------------------

        console.log(
            "Requesting microphone permission..."
        );


        await room.localParticipant.setMicrophoneEnabled(
            true
        );


        microphoneEnabled =
            true;


        console.log(
            "🎤 MICROPHONE ENABLED"
        );


        setVoiceStatus(
            "🎤 Microphone active"
        );


        if (assistantStatus) {

            assistantStatus.textContent =
                "Listening";

        }

        if (assistantSubtitle) {

            assistantSubtitle.textContent =
                'Say "Hey Wolf" or speak naturally.';

        }


        addSystemMessage(
            "🐺 Wolf voice connection is ready."
        );

    }

    catch (error) {

        console.error(
            "LIVEKIT ERROR:",
            error
        );


        livekitConnected =
            false;

        microphoneEnabled =
            false;


        setVoiceStatus(
            "🎤 Microphone connection failed"
        );


        if (assistantStatus) {

            assistantStatus.textContent =
                "Voice connection failed";

        }

        if (assistantSubtitle) {

            assistantSubtitle.textContent =
                error.message;

        }


        addSystemMessage(
            "Voice connection failed: " +
            error.message
        );

    }

}


// ============================================================
// MICROPHONE CONTROL
// ============================================================

async function enableMicrophone() {

    if (!room) {

        console.error(
            "LiveKit room does not exist."
        );

        return;

    }


    try {

        await room.localParticipant
            .setMicrophoneEnabled(
                true
            );

        microphoneEnabled =
            true;

        setVoiceStatus(
            "🎤 Microphone active"
        );

    }

    catch (error) {

        console.error(
            "Microphone enable error:",
            error
        );

        setVoiceStatus(
            "🎤 Microphone permission denied"
        );

    }

}


// ============================================================
// DISABLE MICROPHONE
// ============================================================

async function disableMicrophone() {

    if (!room) {

        return;

    }


    try {

        await room.localParticipant
            .setMicrophoneEnabled(
                false
            );

        microphoneEnabled =
            false;

        setVoiceStatus(
            "🎤 Microphone muted"
        );

    }

    catch (error) {

        console.error(
            "Microphone disable error:",
            error
        );

    }

}


// ============================================================
// VOICE STATUS
// ============================================================

function setVoiceStatus(
    text
) {

    if (voiceStatus) {

        voiceStatus.textContent =
            text;

    }

}


// ============================================================
// TEXT CHAT
// ============================================================

async function sendMessage() {

    if (isSending) {

        return;

    }


    const userText =
        userInput
            ? userInput.value.trim()
            : "";


    if (!userText) {

        return;

    }


    if (!backendReady) {

        addWolfMessage(
            "I am still starting up. Please wait."
        );

        return;

    }


    addUserMessage(
        userText
    );


    if (userInput) {

        userInput.value =
            "";

    }


    await sendToBackend(
        userText
    );

}


// ============================================================
// SEND TO BACKEND
// ============================================================

async function sendToBackend(
    userText
) {

    if (isSending) {

        return;

    }


    isSending =
        true;


    if (sendButton) {

        sendButton.disabled =
            true;

        sendButton.textContent =
            "Thinking...";

    }


    if (assistantStatus) {

        assistantStatus.textContent =
            "Thinking...";

    }


    if (assistantSubtitle) {

        assistantSubtitle.textContent =
            "Wolf is processing your request.";

    }


    try {

        const response =
            await fetch(
                "http://127.0.0.1:5000/ask",
                {

                    method:
                        "POST",

                    headers: {

                        "Content-Type":
                            "application/json"

                    },

                    body:
                        JSON.stringify({

                            message:
                                userText

                        })

                }
            );


        if (!response.ok) {

            throw new Error(
                "Server returned " +
                response.status
            );

        }


        const data =
            await response.json();


        const reply =
            data.reply ||
            "I couldn't generate a response.";


        addWolfMessage(
            reply
        );


        if (
            data.action
        ) {

            console.log(
                "Wolf executed an action."
            );

        }


        if (assistantStatus) {

            assistantStatus.textContent =
                "Wolf is ready";

        }


        if (assistantSubtitle) {

            assistantSubtitle.textContent =
                'Say "Hey Wolf" or type a message.';

        }

    }

    catch (error) {

        console.error(
            "Request error:",
            error
        );


        addWolfMessage(
            "I couldn't connect to my backend."
        );

    }

    finally {

        isSending =
            false;


        if (sendButton) {

            sendButton.disabled =
                false;

            sendButton.textContent =
                "Send";

        }


        if (wolfCircle) {

            wolfCircle.classList.remove(
                "thinking"
            );

        }


        if (userInput) {

            userInput.focus();

        }

    }

}


// ============================================================
// USER MESSAGE
// ============================================================

function addUserMessage(
    message
) {

    if (!chatBox) {

        return;

    }


    const element =
        document.createElement(
            "div"
        );


    element.className =
        "message user-message";


    element.innerHTML = `
        <div class="message-name">
            You
        </div>

        <div class="message-text"></div>
    `;


    element
        .querySelector(
            ".message-text"
        )
        .textContent =
            message;


    chatBox.appendChild(
        element
    );


    scrollChatToBottom();

}


// ============================================================
// WOLF MESSAGE
// ============================================================

function addWolfMessage(
    message
) {

    if (!chatBox) {

        return;

    }


    const element =
        document.createElement(
            "div"
        );


    element.className =
        "message wolf-message";


    element.innerHTML = `
        <div class="message-name">
            Wolf
        </div>

        <div class="message-text"></div>
    `;


    element
        .querySelector(
            ".message-text"
        )
        .textContent =
            message;


    chatBox.appendChild(
        element
    );


    scrollChatToBottom();

}


// ============================================================
// SYSTEM MESSAGE
// ============================================================

function addSystemMessage(
    message
) {

    if (!chatBox) {

        return;

    }


    const element =
        document.createElement(
            "div"
        );


    element.className =
        "system-message";


    element.textContent =
        message;


    chatBox.appendChild(
        element
    );


    scrollChatToBottom();

}


// ============================================================
// SCROLL
// ============================================================

function scrollChatToBottom() {

    if (!chatBox) {

        return;

    }


    chatBox.scrollTop =
        chatBox.scrollHeight;

}


// ============================================================
// ELECTRON IPC
// ============================================================

if (ipcRenderer) {

    ipcRenderer.on(
        "wolf-status",
        (
            event,
            message
        ) => {

            console.log(
                "Wolf IPC:",
                message
            );

        }
    );

}