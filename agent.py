# ============================================================
# WOLF AI DESKTOP ASSISTANT
# agent.py
# ============================================================

import sys
import os
import threading
import asyncio
import random
import webbrowser
import subprocess
import platform
import logging
import urllib.parse

# Make project directory importable
sys.path.append(
    os.path.dirname(os.path.abspath(__file__))
)

# ============================================================
# ENVIRONMENT
# ============================================================

from dotenv import load_dotenv

load_dotenv()

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("wolf")

# ============================================================
# FLASK
# ============================================================

from flask import (
    Flask,
    request,
    jsonify,
    send_from_directory
)

from flask_cors import CORS

# ============================================================
# LIVEKIT API
# ============================================================

from livekit import api

# ============================================================
# LIVEKIT AGENTS
# ============================================================

from livekit import agents

from livekit.agents import (
    Agent,
    AgentSession,
    RoomInputOptions,
    function_tool,
    RunContext,
)

from livekit.plugins import (
    google,
    noise_cancellation
)

# ============================================================
# GEMINI TEXT API
# ============================================================

from google import genai

# ============================================================
# PROJECT FILES
# ============================================================

from promts import (
    AGENT_INSTRUCTION,
    SESSION_INSTRUCTION
)

from tools import (
    open_website,
    get_weather,
    open_default_browser,
    play_music,
    play_youtube_music,
    search_web,
    open_file_explorer
)

# ============================================================
# FLASK APP
# ============================================================

app = Flask(
    __name__,
    static_folder=".",
    static_url_path=""
)

CORS(app)

# ============================================================
# GLOBAL STATE
# ============================================================

AI_READY = False

assistant_session = None

AI_LOCK = threading.Lock()

AGENT_LOOP = None

# ============================================================
# API KEYS
# ============================================================

GOOGLE_API_KEY = (
    os.getenv("GEMINI_API_KEY")
    or os.getenv("GOOGLE_API_KEY")
)

LIVEKIT_URL = os.getenv("LIVEKIT_URL")

LIVEKIT_API_KEY = os.getenv(
    "LIVEKIT_API_KEY"
)

LIVEKIT_API_SECRET = os.getenv(
    "LIVEKIT_API_SECRET"
)

# ============================================================
# GEMINI CLIENT
# ============================================================

gemini_client = None

if GOOGLE_API_KEY:

    try:

        gemini_client = genai.Client(
            api_key=GOOGLE_API_KEY
        )

        AI_READY = True

        logger.info(
            "Gemini text client initialized."
        )

    except Exception as e:

        logger.error(
            f"Gemini initialization failed: {e}"
        )

else:

    logger.error(
        "GOOGLE_API_KEY / GEMINI_API_KEY is missing."
    )

# ============================================================
# LIVEKIT CONFIG CHECK
# ============================================================

if LIVEKIT_URL:
    logger.info(
        f"LiveKit URL configured: {LIVEKIT_URL}"
    )
else:
    logger.error(
        "LIVEKIT_URL is missing."
    )

if LIVEKIT_API_KEY and LIVEKIT_API_SECRET:
    logger.info(
        "LiveKit API credentials configured."
    )
else:
    logger.error(
        "LiveKit API credentials are missing."
    )

# ============================================================
# LIVEKIT TOKEN
# ============================================================

@app.route(
    "/livekit-token",
    methods=["GET"]
)
def livekit_token():

    try:

        if not LIVEKIT_API_KEY:

            return jsonify({
                "error":
                    "LIVEKIT_API_KEY is missing."
            }), 500

        if not LIVEKIT_API_SECRET:

            return jsonify({
                "error":
                    "LIVEKIT_API_SECRET is missing."
            }), 500

        if not LIVEKIT_URL:

            return jsonify({
                "error":
                    "LIVEKIT_URL is missing."
            }), 500

        room_name = (
            "wolf-desktop-room"
        )

        token = (
            api.AccessToken(
                LIVEKIT_API_KEY,
                LIVEKIT_API_SECRET
            )
            .with_identity(
                "wolf-user"
            )
            .with_name(
                "Wolf User"
            )
            .with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=room_name,
                    can_publish=True,
                    can_subscribe=True
                )
            )
        )

        jwt_token = token.to_jwt()

        logger.info(
            "LiveKit token generated."
        )

        return jsonify({

            "token": jwt_token,

            "url": LIVEKIT_URL,

            "room": room_name

        })

    except Exception as e:

        logger.exception(
            "LiveKit token error"
        )

        return jsonify({

            "error": str(e)

        }), 500


# ============================================================
# FRONTEND
# ============================================================

@app.route("/")
def home():

    return send_from_directory(
        ".",
        "index.html"
    )


# ============================================================
# BASIC ACTIONS
# ============================================================

def action_open_google():

    webbrowser.open(
        "https://www.google.com",
        new=2
    )

    return "Google has been opened."


def action_open_youtube():

    webbrowser.open(
        "https://www.youtube.com",
        new=2
    )

    return "YouTube has been opened."


def action_open_gmail():

    webbrowser.open(
        "https://mail.google.com",
        new=2
    )

    return "Gmail has been opened."


def action_search_google(
    query
):

    url = (
        "https://www.google.com/search?q="
        + urllib.parse.quote_plus(query)
    )

    webbrowser.open(
        url,
        new=2
    )

    return (
        f"I searched Google for {query}."
    )


def action_search_youtube(
    query
):

    url = (
        "https://www.youtube.com/results?search_query="
        + urllib.parse.quote_plus(query)
    )

    webbrowser.open(
        url,
        new=2
    )

    return (
        f"I searched YouTube for {query}."
    )


def action_play_youtube(
    query
):

    url = (
        "https://www.youtube.com/results?search_query="
        + urllib.parse.quote_plus(query)
    )

    webbrowser.open(
        url,
        new=2
    )

    logger.info(
        f"YouTube opened for: {query}"
    )

    return (
        f"Opened YouTube and searched for {query}."
    )


def action_open_application(
    application
):

    apps = {

        "notepad":
            "notepad.exe",

        "calculator":
            "calc.exe",

        "calc":
            "calc.exe",

        "paint":
            "mspaint.exe",

        "command prompt":
            "cmd.exe",

        "cmd":
            "cmd.exe",

        "powershell":
            "powershell.exe",

        "explorer":
            "explorer.exe"

    }

    app_name = (
        application
        .lower()
        .strip()
    )

    executable = apps.get(
        app_name
    )

    if not executable:

        return (
            f"I don't have a launcher "
            f"configured for {application}."
        )

    try:

        subprocess.Popen(
            executable,
            shell=True
        )

        logger.info(
            f"Opened application: {application}"
        )

        return (
            f"I opened {application}."
        )

    except Exception as e:

        logger.error(
            f"Application error: {e}"
        )

        return (
            f"I couldn't open {application}."
        )


def action_open_file(
    path
):

    try:

        path = os.path.expanduser(
            path
        )

        if not os.path.exists(path):

            return (
                f"I couldn't find {path}."
            )

        if platform.system() == "Windows":

            os.startfile(path)

        else:

            subprocess.Popen(
                ["xdg-open", path]
            )

        return (
            f"I opened {path}."
        )

    except Exception as e:

        logger.error(
            f"File error: {e}"
        )

        return (
            f"I couldn't open {path}."
        )


def action_create_project_folder(
    name
):

    path = os.path.join(
        os.getcwd(),
        name
    )

    try:

        os.makedirs(
            path,
            exist_ok=True
        )

        return (
            f"Project folder {name} is ready."
        )

    except Exception as e:

        return (
            f"I couldn't create the folder: {e}"
        )


def action_set_timer(
    minutes
):

    try:

        minutes = float(minutes)

    except:

        return (
            "Please provide a valid number of minutes."
        )

    def timer_done():

        logger.info(
            f"Timer finished: {minutes} minute(s)"
        )

        print(
            f"\n🐺 Timer finished: "
            f"{minutes} minute(s)",
            flush=True
        )

    timer = threading.Timer(
        minutes * 60,
        timer_done
    )

    timer.daemon = True

    timer.start()

    return (
        f"Timer set for {minutes} minutes."
    )


def action_motivate_user():

    return random.choice([

        "You got this! Keep going!",

        "Every small step counts!",

        "Stay consistent and keep learning!"

    ])


# ============================================================
# LIVEKIT FUNCTION TOOLS
# ============================================================

@function_tool()
async def open_google(
    context: RunContext
) -> str:

    """Open Google in the default browser."""

    return action_open_google()


@function_tool()
async def open_youtube(
    context: RunContext
) -> str:

    """Open YouTube in the default browser."""

    return action_open_youtube()


@function_tool()
async def open_gmail(
    context: RunContext
) -> str:

    """Open Gmail in the default browser."""

    return action_open_gmail()


@function_tool()
async def search_google(
    context: RunContext,
    query: str
) -> str:

    """Search Google for the requested query."""

    return action_search_google(
        query
    )


@function_tool()
async def search_youtube(
    context: RunContext,
    query: str
) -> str:

    """Search YouTube for a requested video or topic."""

    return action_search_youtube(
        query
    )


@function_tool()
async def play_youtube(
    context: RunContext,
    query: str
) -> str:

    """
    Open YouTube and search for the requested song,
    artist or video.
    """

    return action_play_youtube(
        query
    )


@function_tool()
async def open_application(
    context: RunContext,
    application: str
) -> str:

    """Open a Windows desktop application."""

    return action_open_application(
        application
    )


@function_tool()
async def open_file(
    context: RunContext,
    path: str
) -> str:

    """Open a file or folder."""

    return action_open_file(
        path
    )


@function_tool()
async def create_project_folder(
    context: RunContext,
    name: str
) -> str:

    """Create a folder in the current project directory."""

    return action_create_project_folder(
        name
    )


@function_tool()
async def set_timer(
    context: RunContext,
    minutes: int
) -> str:

    """Set a timer in minutes."""

    return action_set_timer(
        minutes
    )


@function_tool()
async def motivate_user(
    context: RunContext
) -> str:

    """Give the user a short motivational message."""

    return action_motivate_user()


# ============================================================
# EXISTING TOOLS
# ============================================================

AGENT_TOOLS = [

    open_google,

    open_youtube,

    open_gmail,

    search_google,

    search_youtube,

    play_youtube,

    open_website,

    search_web,

    open_application,

    open_file,

    open_file_explorer,

    play_music,

    play_youtube_music,

    get_weather,

    create_project_folder,

    set_timer,

    motivate_user

]


# ============================================================
# TEXT COMMAND ROUTER
#
# This fixes the problem where:
# "Play this song on YouTube"
#
# was answered by Gemini but the tool was never executed.
# ============================================================

def execute_text_action(
    text
):

    original = text.strip()

    lower = original.lower()

    # --------------------------------------------------------
    # PLAY YOUTUBE
    # --------------------------------------------------------

    play_words = [
        "play ",
        "play this song",
        "play song",
        "play music"
    ]

    youtube_words = [
        "youtube",
        "on youtube"
    ]

    if (
        any(
            word in lower
            for word in play_words
        )
        and
        any(
            word in lower
            for word in youtube_words
        )
    ):

        query = lower

        for phrase in [
            "play this song on youtube",
            "play this song on youtube",
            "play on youtube",
            "play on youtube",
            "youtube"
        ]:

            query = query.replace(
                phrase,
                ""
            )

        query = query.strip()

        if not query:

            query = original

        return action_play_youtube(
            query
        )

    # --------------------------------------------------------
    # OPEN GOOGLE
    # --------------------------------------------------------

    if lower in [
        "open google",
        "launch google",
        "start google"
    ]:

        return action_open_google()

    # --------------------------------------------------------
    # OPEN YOUTUBE
    # --------------------------------------------------------

    if lower in [
        "open youtube",
        "launch youtube",
        "start youtube"
    ]:

        return action_open_youtube()

    # --------------------------------------------------------
    # OPEN GMAIL
    # --------------------------------------------------------

    if lower in [
        "open gmail",
        "launch gmail"
    ]:

        return action_open_gmail()

    # --------------------------------------------------------
    # NOTEPAD
    # --------------------------------------------------------

    if (
        "open notepad" in lower
    ):

        return action_open_application(
            "notepad"
        )

    # --------------------------------------------------------
    # CALCULATOR
    # --------------------------------------------------------

    if (
        "open calculator" in lower
        or "open calc" in lower
    ):

        return action_open_application(
            "calculator"
        )

    # --------------------------------------------------------
    # PAINT
    # --------------------------------------------------------

    if (
        "open paint" in lower
    ):

        return action_open_application(
            "paint"
        )

    # --------------------------------------------------------
    # GOOGLE SEARCH
    # --------------------------------------------------------

    if lower.startswith(
        "search google for "
    ):

        query = original[
            len("search google for "):
        ].strip()

        return action_search_google(
            query
        )

    # --------------------------------------------------------
    # YOUTUBE SEARCH
    # --------------------------------------------------------

    if lower.startswith(
        "search youtube for "
    ):

        query = original[
            len("search youtube for "):
        ].strip()

        return action_search_youtube(
            query
        )

    # --------------------------------------------------------
    # NOTHING MATCHED
    # --------------------------------------------------------

    return None


# ============================================================
# GEMINI TEXT
# ============================================================

def ask_gemini_text(
    user_text
):

    if gemini_client is None:

        return (
            "Gemini is not configured. "
            "Please check your API key."
        )

    try:

        logger.info(
            f"TEXT USER: {user_text}"
        )

        response = (
            gemini_client.models.generate_content(

                model="gemini-3.6-flash",

                contents=(

                    AGENT_INSTRUCTION

                    + "\n\n"

                    + """
You are Wolf, a desktop AI assistant.

Answer normal questions clearly and naturally.

Do not claim that you performed a computer action
unless the action has actually been performed.

Computer actions are handled separately by Wolf's
local action system.
"""

                    + "\nUser:\n"

                    + user_text

                )

            )
        )

        reply = (
            response.text
            if response.text
            else
            "I couldn't generate a response."
        )

        logger.info(
            f"TEXT WOLF: {reply}"
        )

        return reply

    except Exception as e:

        logger.exception(
            "Gemini text error"
        )

        return (
            f"I encountered an error: {e}"
        )


# ============================================================
# HEALTH
# ============================================================

@app.route(
    "/health",
    methods=["GET"]
)
def health():

    livekit_ready = bool(
        LIVEKIT_URL
        and LIVEKIT_API_KEY
        and LIVEKIT_API_SECRET
    )

    return jsonify({

        "status": "ok",

        "ai_ready": AI_READY,

        "livekit": livekit_ready,

        "agentic": True,

        "voice": livekit_ready,

        "microphone": livekit_ready

    })


# ============================================================
# TEXT CHAT
# ============================================================

@app.route(
    "/ask",
    methods=["POST"]
)
def ask():

    if not AI_READY:

        return jsonify({

            "reply":
                "Wolf AI is not ready yet.",

            "ready":
                False

        }), 503

    try:

        data = request.get_json(
            silent=True
        )

        if not data:

            return jsonify({

                "reply":
                    "No message received.",

                "ready":
                    True

            }), 400

        user_message = (
            data.get(
                "message",
                ""
            )
            .strip()
        )

        if not user_message:

            return jsonify({

                "reply":
                    "Please tell me what you need.",

                "ready":
                    True

            })

        # ----------------------------------------------------
        # FIRST: TRY REAL LOCAL ACTION
        # ----------------------------------------------------

        with AI_LOCK:

            action_result = (
                execute_text_action(
                    user_message
                )
            )

        if action_result:

            logger.info(
                f"ACTION EXECUTED: {action_result}"
            )

            return jsonify({

                "reply":
                    action_result,

                "ready":
                    True,

                "action":
                    True

            })

        # ----------------------------------------------------
        # OTHERWISE NORMAL GEMINI QUESTION
        # ----------------------------------------------------

        with AI_LOCK:

            result = ask_gemini_text(
                user_message
            )

        return jsonify({

            "reply":
                result,

            "ready":
                True,

            "action":
                False

        })

    except Exception as e:

        logger.exception(
            "/ask error"
        )

        return jsonify({

            "reply":
                f"Error: {e}",

            "ready":
                True

        }), 500


# ============================================================
# LIVEKIT VOICE AGENT
# ============================================================

class Assistant(Agent):

    def __init__(self):

        super().__init__(

            instructions=(

                AGENT_INSTRUCTION

                + """

You are Wolf, a Windows desktop voice assistant.

You are an ACTION-ORIENTED AGENT.

When the user asks you to perform an action,
USE THE AVAILABLE TOOL.

Do NOT simply say that you performed the action.

IMPORTANT TOOL RULES:

1. If the user asks to open Google:
   call open_google.

2. If the user asks to open YouTube:
   call open_youtube.

3. If the user asks to open Gmail:
   call open_gmail.

4. If the user asks to search Google:
   call search_google.

5. If the user asks to search YouTube:
   call search_youtube.

6. If the user asks to PLAY a song, artist, music,
   or video on YouTube:
   call play_youtube.

7. If the user asks to open Notepad:
   call open_application with "notepad".

8. If the user asks to open Calculator:
   call open_application with "calculator".

9. If the user asks to open Paint:
   call open_application with "paint".

10. If the user asks to create a folder:
    call create_project_folder.

11. If the user asks for a timer:
    call set_timer.

12. If the user asks for weather:
    call get_weather.

13. If the user asks to open a website:
    call open_website.

14. If the user asks to open File Explorer:
    call open_file_explorer.

After a tool completes successfully,
briefly tell the user what actually happened.

Never say "I am playing it" before the tool
has actually returned successfully.

For normal questions such as:
"What is AI?"
"What is machine learning?"
"What is CNN?"
answer normally.

Keep voice responses concise and natural.

The user may begin commands with:
"Hey Wolf".

Treat "Hey Wolf" as the wake phrase and ignore
that phrase when interpreting the actual command.
"""

            ),

            tools=AGENT_TOOLS

        )


# ============================================================
# LIVEKIT ENTRYPOINT
# ============================================================

async def entrypoint(
    ctx: agents.JobContext
):

    global assistant_session
    global AGENT_LOOP

    AGENT_LOOP = (
        asyncio.get_running_loop()
    )

    logger.info(
        "===================================="
    )

    logger.info(
        "🐺 WOLF VOICE AGENT STARTING"
    )

    logger.info(
        "===================================="
    )

    # --------------------------------------------------------
    # CONNECT
    # --------------------------------------------------------

    try:

        logger.info(
            "Connecting to LiveKit room..."
        )

        await ctx.connect()

        logger.info(
            f"Connected to room: {ctx.room.name}"
        )

    except Exception as e:

        logger.exception(
            f"LiveKit connection failed: {e}"
        )

        return

    # --------------------------------------------------------
    # CREATE ASSISTANT
    # --------------------------------------------------------

    assistant = Assistant()

    # --------------------------------------------------------
    # CREATE REALTIME GEMINI SESSION
    # --------------------------------------------------------

    try:

        session = AgentSession(

            llm=google.realtime.RealtimeModel(

                model=(
                    "gemini-2.5-flash-native-audio-preview-12-2025"
                ),

                voice="Charon",

                api_key=GOOGLE_API_KEY,

                instructions=(
                    SESSION_INSTRUCTION
                    + """

You are Wolf.

Speak naturally and concisely.

Use tools whenever the user requests a
computer action.

Actually execute the tool before confirming
the action.

If asked to play something on YouTube,
use the play_youtube tool.
"""
                )

            ),

            max_tool_steps=5

        )

        assistant_session = session

    except Exception as e:

        logger.exception(
            f"Failed to create AgentSession: {e}"
        )

        return

    # --------------------------------------------------------
    # START SESSION
    # --------------------------------------------------------

    try:

        logger.info(
            "Starting Wolf voice session..."
        )

        await session.start(

            room=ctx.room,

            agent=assistant,

            room_input_options=RoomInputOptions(

                video_enabled=False,

                noise_cancellation=(
                    noise_cancellation.BVC()
                )

            )

        )

        logger.info(
            "🐺 WOLF VOICE AGENT READY"
        )

        logger.info(
            "Microphone audio is received through LiveKit."
        )

        logger.info(
            "Agentic tools are enabled."
        )

    except Exception as e:

        logger.exception(
            f"AgentSession start failed: {e}"
        )

        assistant_session = None

        return

    # --------------------------------------------------------
    # GREETING
    # --------------------------------------------------------

    try:

        await session.generate_reply(

            instructions=(
                "Say exactly one short friendly "
                "sentence telling the user that "
                "Wolf is ready."
            )

        )

    except Exception as e:

        logger.error(
            f"Greeting error: {e}"
        )

    # --------------------------------------------------------
    # KEEP ALIVE
    # --------------------------------------------------------

    try:

        while True:

            await asyncio.sleep(
                1
            )

    except asyncio.CancelledError:

        assistant_session = None

        logger.info(
            "Wolf voice session ended."
        )


# ============================================================
# FLASK THREAD
# ============================================================

def start_flask():

    logger.info(
        "Starting Flask on "
        "http://127.0.0.1:5000"
    )

    app.run(

        host="127.0.0.1",

        port=5000,

        debug=False,

        use_reloader=False

    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    logger.info(
        "===================================="
    )

    logger.info(
        "Starting Wolf Desktop Assistant"
    )

    logger.info(
        "===================================="
    )

    # --------------------------------------------------------
    # START FLASK
    # --------------------------------------------------------

    flask_thread = threading.Thread(

        target=start_flask,

        daemon=True

    )

    flask_thread.start()

    # --------------------------------------------------------
    # START LIVEKIT AGENT WORKER
    # --------------------------------------------------------

    if len(sys.argv) == 1:

        sys.argv.append(
            "start"
        )

    agents.cli.run_app(

        agents.WorkerOptions(

            entrypoint_fnc=entrypoint,

            port=0

        )

    )