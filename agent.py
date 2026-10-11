# ============================================================
# WOLF AI DESKTOP ASSISTANT
# agent.py
#
# Python backend:
# - Flask API
# - LiveKit token server
# - Gemini text fallback
# - Gemini Realtime voice agent
# - Windows action tools
# - Google / YouTube / Gmail
# - File Explorer
# - Applications
# - File/folder operations
# - Timer
# - Motivation
# - Weather
# - Web search
#
# Voice behavior:
# - Frontend controls microphone.
# - Frontend handles "Hey Wolf".
# - Wolf does NOT automatically greet.
# - After a command finishes, frontend returns to wake mode.
# ============================================================

import os
import sys
import asyncio
import threading
import subprocess
import webbrowser
import logging
import urllib.parse
import time
import random
import re

from pathlib import Path

from dotenv import load_dotenv

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from google import genai

from livekit import api, agents

from livekit.agents import (
    Agent,
    AgentSession,
    RoomInputOptions,
    function_tool,
    RunContext,
)

from livekit.plugins import google, noise_cancellation

from promts import AGENT_INSTRUCTION

from tools import (
    open_website,
    get_weather,
    open_default_browser,
    play_music,
    play_youtube_music,
    search_web,
    open_file_explorer,
)


# ============================================================
# PROJECT PATH
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

load_dotenv(BASE_DIR / ".env")

from backend.orchestrator import AgentOrchestrator



# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="[Wolf] %(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger("wolf")


# ============================================================
# FLASK
# ============================================================

app = Flask(
    __name__,
    static_folder=str(BASE_DIR),
    static_url_path="",
)

CORS(app)


# ============================================================
# GLOBAL STATE
# ============================================================

AI_READY = False
LIVEKIT_READY = False

assistant_session = None
AGENT_LOOP = None


# ============================================================
# ENVIRONMENT
# ============================================================

GOOGLE_API_KEY = (
    os.getenv("GEMINI_API_KEY")
    or os.getenv("GOOGLE_API_KEY")
)

LIVEKIT_URL = os.getenv("LIVEKIT_URL")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")

ROOM_NAME = os.getenv(
    "LIVEKIT_ROOM",
    "wolf-desktop-room",
)

USER_IDENTITY = os.getenv(
    "LIVEKIT_IDENTITY",
    "wolf-user",
)


# ============================================================
# GEMINI CONFIG
# ============================================================

TEXT_MODEL_ENV = os.getenv(
    "GEMINI_TEXT_MODEL",
    "",
).strip()

LIVE_MODEL_ENV = os.getenv(
    "GEMINI_LIVE_MODEL",
    "",
).strip()


# IMPORTANT:
# DO NOT put gemini-2.5-flash-lite here.
#
# Current stable text models.
TEXT_MODEL_CANDIDATES = [
    TEXT_MODEL_ENV,
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.1-flash-lite",
    "gemini-2.5-pro",
    "gemini-flash-latest",
]


# Current realtime models.
#
# LiveKit currently documents Gemini 3.1 realtime.
LIVE_MODELS = [
    LIVE_MODEL_ENV,
    "gemini-3.1-flash-live-preview",
    "gemini-2.5-flash-native-audio-latest",
    "gemini-2.5-flash-native-audio-preview-12-2025",
]


TEXT_MODEL_CANDIDATES = list(
    dict.fromkeys(
        model
        for model in TEXT_MODEL_CANDIDATES
        if model
    )
)

LIVE_MODELS = list(
    dict.fromkeys(
        model
        for model in LIVE_MODELS
        if model
    )
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
            "Gemini client initialized."
        )

    except Exception as e:

        logger.exception(
            "Gemini client initialization failed: %s",
            e,
        )

else:

    logger.warning(
        "GEMINI_API_KEY / GOOGLE_API_KEY not found."
    )


# ============================================================
# UTILITY
# ============================================================

def normalize_text(value):

    if value is None:
        return ""

    return str(value).strip()


def safe_url(value):

    value = normalize_text(value)

    if not value:
        return ""

    if not value.startswith(
        ("http://", "https://")
    ):
        value = "https://" + value

    return value


def clean_model_name(model_name):

    return normalize_text(
        model_name
    ).replace(
        "models/",
        "",
    )


# ============================================================
# WINDOWS ACTIONS
# ============================================================

def action_open_google():

    try:

        url = "https://www.google.com/"

        success = webbrowser.open(
            url,
            new=2,
        )

        if not success:

            return (
                False,
                "Google could not be opened, Sir.",
            )

        logger.info(
            "Opened Google."
        )

        return (
            True,
            "Google has been opened, Sir.",
        )

    except Exception as e:

        logger.exception(
            "Google open failed."
        )

        return (
            False,
            f"I could not open Google, Sir. {e}",
        )


# ============================================================

def action_open_youtube():

    try:

        url = "https://www.youtube.com/"

        success = webbrowser.open(
            url,
            new=2,
        )

        if not success:

            return (
                False,
                "YouTube could not be opened, Sir.",
            )

        logger.info(
            "Opened YouTube."
        )

        return (
            True,
            "YouTube has been opened, Sir.",
        )

    except Exception as e:

        logger.exception(
            "YouTube open failed."
        )

        return (
            False,
            f"I could not open YouTube, Sir. {e}",
        )


# ============================================================

def action_open_gmail():

    try:

        url = "https://mail.google.com/"

        success = webbrowser.open(
            url,
            new=2,
        )

        if not success:

            return (
                False,
                "Gmail could not be opened, Sir.",
            )

        return (
            True,
            "Gmail has been opened, Sir.",
        )

    except Exception as e:

        logger.exception(
            "Gmail open failed."
        )

        return (
            False,
            f"I could not open Gmail, Sir. {e}",
        )


# ============================================================

def action_search_google(query):

    query = normalize_text(query)

    if not query:

        return (
            False,
            "Please tell me what you want to search for, Sir.",
        )

    try:

        encoded = urllib.parse.quote_plus(
            query
        )

        url = (
            "https://www.google.com/search?q="
            + encoded
        )

        success = webbrowser.open(
            url,
            new=2,
        )

        if not success:

            return (
                False,
                "Google search could not be opened, Sir.",
            )

        logger.info(
            "Google search: %s",
            query,
        )

        return (
            True,
            f"I searched Google for {query}, Sir.",
        )

    except Exception as e:

        logger.exception(
            "Google search failed."
        )

        return (
            False,
            f"Google search failed, Sir. {e}",
        )


# ============================================================

def action_search_youtube(query):

    query = normalize_text(query)

    if not query:

        return (
            False,
            "Please tell me what to search on YouTube, Sir.",
        )

    try:

        encoded = urllib.parse.quote_plus(
            query
        )

        url = (
            "https://www.youtube.com/results"
            "?search_query="
            + encoded
        )

        success = webbrowser.open(
            url,
            new=2,
        )

        if not success:

            return (
                False,
                "YouTube search could not be opened, Sir.",
            )

        logger.info(
            "YouTube search: %s",
            query,
        )

        return (
            True,
            f"I searched YouTube for {query}, Sir.",
        )

    except Exception as e:

        logger.exception(
            "YouTube search failed."
        )

        return (
            False,
            f"YouTube search failed, Sir. {e}",
        )


# ============================================================

def action_play_youtube(query):

    query = normalize_text(query)

    if not query:

        return (
            False,
            "Please tell me what you want to play, Sir.",
        )

    try:

        encoded = urllib.parse.quote_plus(
            query
        )

        url = (
            "https://www.youtube.com/results"
            "?search_query="
            + encoded
        )

        success = webbrowser.open(
            url,
            new=2,
        )

        if not success:

            return (
                False,
                "YouTube could not be opened, Sir.",
            )

        return (
            True,
            f"I opened YouTube results for {query}, Sir.",
        )

    except Exception as e:

        logger.exception(
            "YouTube playback request failed."
        )

        return (
            False,
            f"I could not open YouTube, Sir. {e}",
        )


# ============================================================
# APPLICATION CONTROL
# ============================================================

def action_open_application(application):

    application = normalize_text(
        application
    ).lower()

    aliases = {

        "notepad": "notepad.exe",

        "calculator": "calc.exe",
        "calc": "calc.exe",

        "paint": "mspaint.exe",

        "cmd": "cmd.exe",
        "command prompt": "cmd.exe",

        "powershell": "powershell.exe",
        "power shell": "powershell.exe",

        "file explorer": "explorer.exe",
        "explorer": "explorer.exe",

    }

    executable = aliases.get(
        application
    )

    if not executable:

        return (
            False,
            f"I don't have a Windows launcher configured "
            f"for {application}, Sir.",
        )

    try:

        subprocess.Popen(
            [executable],
            shell=False,
        )

        logger.info(
            "Opened application: %s",
            application,
        )

        return (
            True,
            f"{application.title()} has been opened, Sir.",
        )

    except Exception as e:

        logger.exception(
            "Application launch failed."
        )

        return (
            False,
            f"I could not open {application}, Sir. {e}",
        )


# ============================================================
# FILE OPERATIONS
# ============================================================

def action_open_file(path):

    path = normalize_text(path)

    if not path:

        return (
            False,
            "Please provide a file path, Sir.",
        )

    try:

        path = os.path.expandvars(
            os.path.expanduser(path)
        )

        if not os.path.exists(path):

            return (
                False,
                f"I could not find {path}, Sir.",
            )

        os.startfile(path)

        return (
            True,
            f"I opened {path}, Sir.",
        )

    except Exception as e:

        logger.exception(
            "File opening failed."
        )

        return (
            False,
            f"I could not open that file, Sir. {e}",
        )


# ============================================================


def action_create_project_folder(name):

    name = normalize_text(name)

    if not name:

        return (
            False,
            "Please tell me the folder name, Sir.",
        )

    try:

        safe_name = "".join(
            c
            for c in name
            if c.isalnum()
            or c in (
                " ",
                "_",
                "-",
            )
        ).strip()

        if not safe_name:

            return (
                False,
                "That folder name is not valid, Sir.",
            )

        project_root = (
            Path.home()
            / "Desktop"
            / "Wolf Projects"
        )

        project_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        folder = (
            project_root
            / safe_name
        )

        folder.mkdir(
            parents=True,
            exist_ok=True,
        )

        logger.info(
            "Created folder: %s",
            folder,
        )

        return (
            True,
            f"The folder '{safe_name}' has been created "
            f"on your Desktop under Wolf Projects, Sir.",
        )

    except Exception as e:

        logger.exception(
            "Folder creation failed."
        )

        return (
            False,
            f"I could not create the folder, Sir. {e}",
        )


# ============================================================

def action_create_file(folder_name, file_name, content=""):
    """Create a file inside a Wolf Projects folder."""

    folder_name = normalize_text(folder_name)
    file_name = normalize_text(file_name)

    if not folder_name:
        return (False, "Please tell me the folder name, Sir.")
    if not file_name:
        return (False, "Please tell me the file name, Sir.")

    try:

        safe_folder = "".join(
            c for c in folder_name if c.isalnum() or c in (" ", "_", "-")
        ).strip()

        safe_file = "".join(
            c for c in file_name if c.isalnum() or c in (" ", "_", "-", ".")
        ).strip()

        if not safe_folder:
            return (False, "That folder name is not valid, Sir.")
        if not safe_file:
            return (False, "That file name is not valid, Sir.")

        project_root = Path.home() / "Desktop" / "Wolf Projects"
        folder = project_root / safe_folder
        folder.mkdir(parents=True, exist_ok=True)

        file_path = folder / safe_file
        file_path.write_text(content or "", encoding="utf-8")

        logger.info("Created file: %s", file_path)

        return (
            True,
            f"I created '{safe_file}' inside '{safe_folder}', Sir.",
        )

    except Exception as e:

        logger.exception("File creation failed.")

        return (
            False,
            f"I could not create the file, Sir. {e}",
        )



# ============================================================
# TIMER
# ============================================================

def action_set_timer(minutes):

    try:

        minutes = float(minutes)

        if minutes <= 0:

            return (
                False,
                "The timer must be greater than zero, Sir.",
            )

        seconds = minutes * 60

        def timer_finished():

            logger.info(
                "Timer finished: %s minutes",
                minutes,
            )

            try:

                import winsound

                for _ in range(3):

                    winsound.Beep(
                        1000,
                        500,
                    )

            except Exception:

                print(
                    "\n[Wolf] Timer finished!"
                )

        timer = threading.Timer(
            seconds,
            timer_finished,
        )

        timer.daemon = True
        timer.start()

        return (
            True,
            f"Timer set for {minutes:g} minutes, Sir.",
        )

    except Exception as e:

        logger.exception(
            "Timer creation failed."
        )

        return (
            False,
            f"I could not set the timer, Sir. {e}",
        )


# ============================================================
# MOTIVATION
# ============================================================

def action_motivate_user():

    messages = [

        "You've got this, Sir. One focused step at a time.",

        "Keep going. Progress comes from consistency, Sir.",

        "Don't wait for perfect. Build, test, improve, repeat.",

        "Your future self will thank you for the work you do today.",

        "Stay focused, Sir. You're closer than you think.",

    ]

    return (
        True,
        random.choice(messages),
    )


# ============================================================
# WEATHER
# ============================================================

def action_get_weather(city):

    city = normalize_text(city)

    if not city:

        return (
            False,
            "Please tell me the city, Sir.",
        )

    try:

        from langchain_community.tools import (
            DuckDuckGoSearchRun
        )

        query = (
            f"current weather in {city}"
        )

        result = DuckDuckGoSearchRun().run(
            tool_input=query
        )

        if result:

            return (
                True,
                f"{result}, Sir.",
            )

        return (
            False,
            f"I could not find the current weather "
            f"for {city}, Sir.",
        )

    except Exception as e:

        logger.exception(
            "Weather lookup failed."
        )

        return (
            False,
            f"I could not retrieve the weather, Sir. {e}",
        )


# ============================================================
# OPEN WEBSITE
# ============================================================

def action_open_website(url):

    url = safe_url(url)

    if not url:

        return (
            False,
            "Please provide a website address, Sir.",
        )

    try:

        success = webbrowser.open(
            url,
            new=2,
        )

        if not success:

            return (
                False,
                f"I could not open {url}, Sir.",
            )

        return (
            True,
            f"Opened {url}, Sir.",
        )

    except Exception as e:

        logger.exception(
            "Website opening failed."
        )

        return (
            False,
            f"I could not open {url}, Sir. {e}",
        )


# ============================================================
# LIVEKIT FUNCTION TOOLS
# ============================================================

@function_tool()
async def open_google(
    context: RunContext,
) -> str:

    return action_open_google()[1]


@function_tool()
async def open_youtube(
    context: RunContext,
) -> str:

    return action_open_youtube()[1]


@function_tool()
async def open_gmail(
    context: RunContext,
) -> str:

    return action_open_gmail()[1]


@function_tool()
async def search_google(
    context: RunContext,
    query: str,
) -> str:

    return action_search_google(query)[1]


@function_tool()
async def search_youtube(
    context: RunContext,
    query: str,
) -> str:

    return action_search_youtube(query)[1]


@function_tool()
async def play_youtube(
    context: RunContext,
    query: str,
) -> str:

    return action_play_youtube(query)[1]


@function_tool()
async def open_application(
    context: RunContext,
    application: str,
) -> str:

    return action_open_application(application)[1]


@function_tool()
async def open_file(
    context: RunContext,
    path: str,
) -> str:

    return action_open_file(path)[1]


@function_tool()
async def create_project_folder(
    context: RunContext,
    name: str,
) -> str:

    return action_create_project_folder(name)[1]


@function_tool()
async def set_timer(
    context: RunContext,
    minutes: float,
) -> str:

    return action_set_timer(minutes)[1]


@function_tool()
async def motivate_user(
    context: RunContext,
) -> str:

    return action_motivate_user()[1]


@function_tool()
async def get_weather_action(
    context: RunContext,
    city: str,
) -> str:

    return action_get_weather(city)[1]


@function_tool()
async def open_website_action(
    context: RunContext,
    url: str,
) -> str:

    return action_open_website(url)[1]


@function_tool()
async def create_file_action(
    context: RunContext,
    folder_name: str,
    file_name: str,
    content: str = "",
) -> str:
    """Create a new file inside a Wolf Projects folder on the Desktop."""

    return action_create_file(folder_name, file_name, content)[1]


# ============================================================
# AGENT TOOL LIST
# ============================================================

AGENT_TOOLS = [

    # Existing tools.py tools
    open_website,
    get_weather,
    open_default_browser,
    play_music,
    play_youtube_music,
    search_web,
    open_file_explorer,

    # Local Windows tools
    open_google,
    open_youtube,
    open_gmail,
    search_google,
    search_youtube,
    play_youtube,
    open_application,
    open_file,
    create_project_folder,
    create_file_action,
    set_timer,
    motivate_user,
    get_weather_action,
    open_website_action,
]



# ============================================================
# TEXT MODEL DISCOVERY
# ============================================================

def find_text_model():

    if not gemini_client:
        return None

    try:
        logger.info(
            "Checking available Gemini text models..."
        )

        models = gemini_client.models.list()
        available = []

        for model in models:
            name = getattr(
                model,
                "name",
                "",
            )
            if name:
                available.append(
                    clean_model_name(name)
                )

        logger.info(
            "Available Gemini models (%d found): %s",
            len(available),
            available[:20],
        )

        candidates = []
        if TEXT_MODEL_ENV:
            candidates.append(clean_model_name(TEXT_MODEL_ENV))
        for c in TEXT_MODEL_CANDIDATES:
            cand_clean = clean_model_name(c)
            if cand_clean and cand_clean not in candidates:
                candidates.append(cand_clean)

        for candidate_short in candidates:
            if candidate_short in available:
                try:
                    gemini_client.models.generate_content(
                        model=candidate_short,
                        contents="ping",
                    )
                    logger.info(
                        "Selected verified responsive model: %s",
                        candidate_short,
                    )
                    return candidate_short
                except Exception as ping_err:
                    logger.warning(
                        "Candidate model %s failed ping (%s), trying next...",
                        candidate_short,
                        ping_err,
                    )
                    continue

        for model_name in available:
            lower = model_name.lower()
            if (
                "gemini" in lower
                and "flash" in lower
                and "embedding" not in lower
                and "live" not in lower
                and "native-audio" not in lower
            ):
                return model_name

        return "gemini-3.5-flash-lite"

    except Exception as e:
        logger.warning(
            "Could not discover text models: %s",
            e,
        )

    if TEXT_MODEL_ENV:
        return clean_model_name(TEXT_MODEL_ENV)

    return "gemini-3.5-flash-lite"



TEXT_MODEL = find_text_model()

logger.info(
    "Selected text model: %s",
    TEXT_MODEL,
)

orchestrator = AgentOrchestrator(
    gemini_client=gemini_client,
    model_name=TEXT_MODEL or "gemini-3.8-flash",
)



# ============================================================
# GEMINI TEXT
# ============================================================

def ask_gemini_text(prompt: str) -> str:

    if not gemini_client:

        return (
            "Gemini is not configured, Sir. "
            "Please check your API key."
        )

    models = []

    if TEXT_MODEL:

        models.append(
            clean_model_name(TEXT_MODEL)
        )

    for model in TEXT_MODEL_CANDIDATES:

        models.append(
            clean_model_name(model)
        )

    # Remove duplicates.
    models = list(
        dict.fromkeys(models)
    )

    last_error = None

    for model_name in models:

        for attempt in range(2):

            try:

                logger.info(
                    "Gemini text request: "
                    "model=%s attempt=%s",
                    model_name,
                    attempt + 1,
                )

                response = (
                    gemini_client
                    .models
                    .generate_content(
                        model=model_name,
                        contents=prompt,
                    )
                )

                text = getattr(
                    response,
                    "text",
                    None,
                )

                if text:

                    logger.info(
                        "Gemini text response received "
                        "from %s",
                        model_name,
                    )

                    return text.strip()

                logger.warning(
                    "Gemini returned an empty response "
                    "from %s",
                    model_name,
                )

                break

            except Exception as exc:

                last_error = exc

                error_text = str(exc)

                logger.warning(
                    "Gemini text error "
                    "(model=%s attempt=%s): %s",
                    model_name,
                    attempt + 1,
                    error_text,
                )

                upper_error = error_text.upper()

                # ------------------------------------------------
                # MODEL DOES NOT EXIST / NOT AVAILABLE
                # ------------------------------------------------

                if (
                    "404" in error_text
                    or "NOT_FOUND" in upper_error
                    or "NO LONGER AVAILABLE" in upper_error
                ):

                    logger.warning(
                        "Skipping unavailable model: %s",
                        model_name,
                    )

                    break

                # ------------------------------------------------
                # TEMPORARY RATE / SERVER ERROR
                # ------------------------------------------------

                if (
                    "429" in error_text
                    or "503" in error_text
                    or "UNAVAILABLE" in upper_error
                    or "RESOURCE_EXHAUSTED" in upper_error
                    or "TOO MANY REQUESTS" in upper_error
                ):

                    wait_time = (
                        3 * (2 ** attempt)
                    )

                    logger.info(
                        "Temporary Gemini error. "
                        "Waiting %s seconds...",
                        wait_time,
                    )

                    time.sleep(
                        wait_time
                    )

                    continue

                # ------------------------------------------------
                # AUTH ERROR
                # ------------------------------------------------

                if (
                    "401" in error_text
                    or "403" in error_text
                    or "PERMISSION_DENIED" in upper_error
                    or "UNAUTHENTICATED" in upper_error
                ):

                    logger.error(
                        "Gemini API authentication/"
                        "permission error."
                    )

                    return (
                        "Gemini authentication failed, Sir. "
                        "Please check your API key."
                    )

                # ------------------------------------------------
                # OTHER ERROR
                # ------------------------------------------------

                break

    logger.error(
        "All Gemini text models failed. "
        "Last error: %s",
        last_error,
    )

    return (
        "Sorry, Sir. Gemini is temporarily unavailable. "
        "Please try again in a moment."
    )


# ============================================================
# TEXT ACTION ROUTER
# ============================================================

def execute_text_action(text):

    original = normalize_text(text)
    lower = original.lower()

    # Strip common voice filler prefixes
    def strip_filler(s):
        for filler in (
            "please ", "can you ", "could you ", "would you ",
            "wolf ", "hey wolf ", "i want to ", "i'd like to ",
            "i want you to ", "i need you to ",
        ):
            if s.startswith(filler):
                s = s[len(filler):]
        return s

    clean = strip_filler(lower)

    # ========================================================
    # GOOGLE homepage
    # ========================================================

    google_home = {"open google", "open google.com", "launch google", "go to google", "visit google"}
    if lower in google_home or clean in google_home:
        return action_open_google()[1]

    # ========================================================
    # YOUTUBE homepage
    # ========================================================

    yt_home = {"open youtube", "launch youtube", "open youtube.com", "go to youtube", "visit youtube"}
    if lower in yt_home or clean in yt_home:
        return action_open_youtube()[1]

    # ========================================================
    # GMAIL
    # ========================================================

    gmail_home = {"open gmail", "open email", "open google mail", "launch gmail", "go to gmail"}
    if lower in gmail_home or clean in gmail_home:
        return action_open_gmail()[1]

    # ========================================================
    # FILE EXPLORER
    # ========================================================

    explorer_triggers = {
        "open file explorer", "open explorer", "open files",
        "open file manager", "file explorer", "show files",
        "open my files", "show my files",
    }
    if lower in explorer_triggers or clean in explorer_triggers or "file explorer" in lower:
        try:
            subprocess.Popen(["explorer.exe", "/n,", "C:\\"])
            return "File Explorer has been opened, Sir."
        except Exception as e:
            return f"I could not open File Explorer, Sir. {e}"

    # ========================================================
    # APPLICATIONS
    # ========================================================

    app_names = [
        "notepad", "calculator", "calc", "paint",
        "command prompt", "cmd", "powershell",
    ]

    for app_name in app_names:
        for candidate in (lower, clean):
            if candidate in (
                f"open {app_name}",
                f"launch {app_name}",
                f"start {app_name}",
                f"run {app_name}",
            ):
                return action_open_application(app_name)[1]

    # ========================================================
    # GOOGLE SEARCH  — expanded patterns
    # ========================================================

    google_prefixes = [
        "search google for ",
        "search for ",
        "search google ",
        "google search for ",
        "google search ",
        "google ",
        "search on google for ",
        "search on google ",
        "do a google search for ",
        "look up on google ",
        "look up ",
    ]

    for prefix in google_prefixes:
        for src_lower, src_orig in ((lower, original), (clean, original[len(lower) - len(clean):] if len(lower) > len(clean) else original)):
            if src_lower.startswith(prefix):
                query = src_orig[len(prefix):].strip()
                if query:
                    return action_search_google(query)[1]

    # ========================================================
    # YOUTUBE SEARCH
    # ========================================================

    youtube_prefixes = [
        "search youtube for ",
        "search youtube ",
        "youtube search for ",
        "youtube search ",
        "search on youtube for ",
        "search on youtube ",
    ]

    for prefix in youtube_prefixes:
        for src_lower, src_orig in ((lower, original), (clean, original[len(lower) - len(clean):] if len(lower) > len(clean) else original)):
            if src_lower.startswith(prefix):
                query = src_orig[len(prefix):].strip()
                if query:
                    return action_search_youtube(query)[1]

    # ========================================================
    # PLAY YOUTUBE
    # ========================================================

    if "youtube" in lower and (lower.startswith("play") or clean.startswith("play")):
        query = lower if lower.startswith("play") else clean
        for phrase in ("play on youtube", "play youtube", "play"):
            query = query.replace(phrase, "", 1)
        query = query.strip()
        if query:
            return action_play_youtube(query)[1]

    # ========================================================
    # MULTI-STEP: Create folder AND file inside it
    # ========================================================

    multi_match = re.search(
        r"(?:create|make)\s+(?:a\s+)?folder\s+"
        r"(?:called\s+|named\s+)?[\"']?([A-Za-z0-9 _\-]+?)[\"']?"
        r"\s+and\s+(?:create\s+)?(?:a\s+)?file\s+"
        r"(?:called\s+|named\s+)?[\"']?([A-Za-z0-9 _\-\.]+?)[\"']?"
        r"(?:\s+inside\s+it|\s+in\s+it|\s+inside\s+the\s+folder)?$",
        lower,
    )

    if multi_match:
        folder_name = multi_match.group(1).strip()
        file_name = multi_match.group(2).strip()
        if folder_name and file_name:
            folder_result = action_create_project_folder(folder_name)
            if folder_result[0]:
                file_result = action_create_file(folder_name, file_name)
                return f"{folder_result[1]} {file_result[1]}"
            return folder_result[1]

    # ========================================================
    # CREATE FOLDER (single)
    # ========================================================

    folder_prefixes = [
        "create folder ",
        "make folder ",
        "create a folder ",
        "make a folder ",
        "create a folder called ",
        "make a folder called ",
        "create folder called ",
        "make folder called ",
        "create a new folder called ",
        "create a new folder named ",
        "create a folder named ",
    ]

    for prefix in folder_prefixes:
        for src_lower, src_orig in ((lower, original), (clean, original[len(lower) - len(clean):] if len(lower) > len(clean) else original)):
            if src_lower.startswith(prefix):
                name = src_orig[len(prefix):].strip()
                name = re.sub(
                    r"\s+(?:on\s+(?:the\s+)?desktop|in\s+wolf\s+projects|on\s+my\s+desktop)$",
                    "",
                    name,
                    flags=re.IGNORECASE,
                ).strip()
                if name:
                    return action_create_project_folder(name)[1]

    # ========================================================
    # CREATE FILE (standalone)
    # ========================================================

    file_prefixes = [
        "create file ",
        "make file ",
        "create a file ",
        "make a file ",
        "create a file called ",
        "make a file called ",
        "create file called ",
    ]

    for prefix in file_prefixes:
        for src_lower, src_orig in ((lower, original), (clean, original[len(lower) - len(clean):] if len(lower) > len(clean) else original)):
            if src_lower.startswith(prefix):
                remainder = src_orig[len(prefix):].strip()
                m = re.match(r"^(.+?)\s+(?:inside|in)\s+(?:folder\s+)?(.+)$", remainder, re.IGNORECASE)
                if m:
                    file_name = m.group(1).strip()
                    folder_name = m.group(2).strip()
                else:
                    file_name = remainder
                    folder_name = "General"
                if file_name:
                    return action_create_file(folder_name, file_name)[1]

    # ========================================================
    # TIMER
    # ========================================================

    if "timer" in lower:
        match = re.search(
            r"(\d+(?:\.\d+)?)\s*(minute|minutes|min|mins|hour|hours|second|seconds|sec|secs)",
            lower,
        )
        if match:
            quantity = float(match.group(1))
            unit = match.group(2)
            if "hour" in unit:
                minutes = quantity * 60
            elif "sec" in unit:
                minutes = quantity / 60
            else:
                minutes = quantity
            return action_set_timer(minutes)[1]

    # ========================================================
    # MOTIVATION
    # ========================================================

    if "motivate me" in lower or "motivation" in lower or "give me motivation" in lower or "inspire me" in lower:
        return action_motivate_user()[1]

    # ========================================================
    # WEBSITE
    # ========================================================

    for pfx in ("open website ", "open site ", "open url ", "go to ", "visit "):
        for src_lower, src_orig in ((lower, original), (clean, original[len(lower) - len(clean):] if len(lower) > len(clean) else original)):
            if src_lower.startswith(pfx):
                url = src_orig[len(pfx):].strip()
                if url and ("." in url or url.startswith("http")):
                    return action_open_website(url)[1]

    # ========================================================
    # WEATHER
    # ========================================================

    weather_prefixes = [
        "weather in ",
        "what is the weather in ",
        "what's the weather in ",
        "check weather in ",
        "what is the weather like in ",
        "what's the weather like in ",
        "weather for ",
        "weather at ",
        "weather today in ",
    ]

    for prefix in weather_prefixes:
        for src_lower, src_orig in ((lower, original), (clean, original[len(lower) - len(clean):] if len(lower) > len(clean) else original)):
            if src_lower.startswith(prefix):
                city = src_orig[len(prefix):].strip()
                if city:
                    return action_get_weather(city)[1]

    return None


# ============================================================
# FLASK ROUTES
# ============================================================

@app.route(
    "/health",
    methods=["GET"],
)
def health():

    return jsonify({

        "ok": True,

        "ai_ready": AI_READY,

        "livekit": bool(
            LIVEKIT_URL
            and LIVEKIT_API_KEY
            and LIVEKIT_API_SECRET
        ),

        "agentic": True,

        "voice": True,

        "microphone": "frontend-controlled",

        "text_model": TEXT_MODEL,

        "live_models": LIVE_MODELS,

    })


# ============================================================

@app.route(
    "/livekit-token",
    methods=["GET"],
)
def livekit_token():

    if not (
        LIVEKIT_API_KEY
        and LIVEKIT_API_SECRET
        and LIVEKIT_URL
    ):

        return jsonify({
            "error": (
                "LiveKit environment variables "
                "are not configured."
            )
        }), 500

    try:

        token = api.AccessToken(
            LIVEKIT_API_KEY,
            LIVEKIT_API_SECRET,
        )

        token.with_identity(
            USER_IDENTITY
        )

        token.with_name(
            "Wolf User"
        )

        token.with_grants(
            api.VideoGrants(
                room_join=True,
                room=ROOM_NAME,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )

        jwt_token = token.to_jwt()

        return jsonify({

            "token": jwt_token,

            "url": LIVEKIT_URL,

            "room": ROOM_NAME,

            "identity": USER_IDENTITY,

        })

    except Exception as e:

        logger.exception(
            "LiveKit token creation failed."
        )

        return jsonify({
            "error": str(e)
        }), 500


# ============================================================

@app.route(
    "/",
    methods=["GET"],
)
def home():

    return send_from_directory(
        BASE_DIR,
        "index.html",
    )


# ============================================================
# AUDIO TRANSCRIPTION ENDPOINT
# ============================================================

@app.route(
    "/transcribe-audio",
    methods=["POST"],
)
def transcribe_audio():
    """
    Transcribes audio recorded via standard HTML5 MediaRecorder (WebM/WAV)
    using Gemini multimodal audio transcription with GOOGLE_API_KEY.
    Returns: {"ok": True, "text": "transcribed text"} or {"ok": True, "text": "", "empty": True}
    """
    if not gemini_client:
        return jsonify({
            "ok": False,
            "error": "Gemini client is not configured.",
        }), 500

    audio_file = request.files.get("audio")
    if not audio_file:
        return jsonify({
            "ok": False,
            "error": "No audio file provided in request.",
        }), 400

    audio_bytes = audio_file.read()
    if not audio_bytes or len(audio_bytes) < 100:
        return jsonify({
            "ok": True,
            "text": "",
            "empty": True,
        })

    mime_type = audio_file.content_type or "audio/webm"
    if "webm" in mime_type:
        mime_type = "audio/webm"
    elif "wav" in mime_type:
        mime_type = "audio/wav"

    from google.genai import types

    candidates = [TEXT_MODEL, "gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-2.5-pro"]
    candidates = [c for c in candidates if c]

    for model_name in candidates:
        try:
            logger.info("Transcribing audio (%d bytes) with model: %s", len(audio_bytes), model_name)
            resp = gemini_client.models.generate_content(
                model=model_name,
                contents=[
                    types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                    "Transcribe the spoken audio verbatim into English text. Output only the exact words spoken. Do not add conversational filler, notes, quotes, or markdown. If the audio is silent or contains no discernible speech, output: EMPTY",
                ],
            )
            raw = (getattr(resp, "text", "") or "").strip()
            if not raw or raw.upper() == "EMPTY":
                return jsonify({
                    "ok": True,
                    "text": "",
                    "empty": True,
                })

            clean_text = raw.strip('"\'').strip()
            logger.info("Transcription result: %s", clean_text)
            return jsonify({
                "ok": True,
                "text": clean_text,
            })

        except Exception as exc:
            logger.warning("Transcription attempt with %s failed: %s", model_name, exc)
            continue

    return jsonify({
        "ok": False,
        "error": "All transcription model candidates failed.",
    }), 503


# ============================================================

@app.route(
    "/ask",
    methods=["POST"],
)
def ask():

    data = request.get_json(
        silent=True
    ) or {}

    text = normalize_text(
        data.get("message")
    )

    if not text:

        return jsonify({
            "ok": False,
            "error": "Message is empty.",
        }), 400

    logger.info(
        "Text request: %s",
        text,
    )

    # --------------------------------------------------------
    # AGENTIC ORCHESTRATION (FAST PATH -> AGENTIC PATH -> AI)
    # --------------------------------------------------------

    try:

        result = orchestrator.process_command(text)

        return jsonify(result)

    except Exception as e:

        logger.exception(
            "Orchestrator request error: %s",
            e,
        )

        return jsonify({

            "ok": False,

            "success": False,

            "type": "error",

            "error": str(e),

            "message": f"Sorry Sir, I encountered an error: {e}",

        }), 500



# ============================================================
# LIVE REALTIME MODEL
# ============================================================

def create_realtime_model(
    model_name
):

    if not GOOGLE_API_KEY:

        raise RuntimeError(
            "Gemini API key is missing."
        )

    instructions = f"""
{AGENT_INSTRUCTION}

VOICE MODE:

- The frontend controls the "Hey Wolf" wake word.
- Do not greet automatically.
- When the frontend activates the microphone, the user's speech
  should be treated as a command.
- Execute the appropriate tool before saying an action is complete.
- Never pretend an action succeeded.
- Keep simple responses short.
- Use search_web for web/research/latest information.
- Use search_google when Google search is explicitly requested.
- Use search_youtube for YouTube searches.
- Use play_youtube when the user asks to play something on YouTube.
"""

    logger.info(
        "Creating Gemini realtime model: %s",
        model_name,
    )

    return google.realtime.RealtimeModel(

        model=model_name,

        voice="Charon",

        api_key=GOOGLE_API_KEY,

        instructions=instructions,

    )


# ============================================================
# VOICE SESSION
# ============================================================

async def start_voice_session(
    ctx,
    assistant,
):

    global assistant_session

    last_error = None

    for model_name in LIVE_MODELS:

        for attempt in range(2):

            try:

                logger.info(
                    "Trying Gemini realtime model "
                    "%s (attempt %s/2)",
                    model_name,
                    attempt + 1,
                )

                realtime_model = (
                    create_realtime_model(
                        model_name
                    )
                )

                session = AgentSession(

                    llm=realtime_model,

                    max_tool_steps=5,

                )

                @session.on(
                    "user_input_transcribed"
                )
                def on_user_transcription(
                    event
                ):

                    try:

                        logger.info(
                            "USER TRANSCRIPT: %s | final=%s",
                            event.transcript,
                            event.is_final,
                        )

                    except Exception:
                        pass

                @session.on(
                    "conversation_item_added"
                )
                def on_conversation_item(
                    event
                ):

                    try:

                        logger.debug(
                            "Conversation item added: %s",
                            event.item,
                        )

                    except Exception:
                        pass

                await session.start(

                    assistant,

                    room=ctx.room,

                    room_input_options=RoomInputOptions(

                        video_enabled=False,

                        audio_enabled=True,

                        text_enabled=True,

                        noise_cancellation=(
                            noise_cancellation.BVC()
                        ),

                    ),

                )

                assistant_session = session

                logger.info(
                    "Wolf realtime session started "
                    "with model: %s",
                    model_name,
                )

                # IMPORTANT:
                # No generate_reply().
                #
                # Frontend controls the wake word.

                return session

            except Exception as e:

                last_error = e

                logger.warning(
                    "Realtime model %s failed: %s",
                    model_name,
                    e,
                )

                await asyncio.sleep(
                    2 * (attempt + 1)
                )

    raise RuntimeError(
        "All realtime models failed. "
        f"Last error: {last_error}"
    )


# ============================================================
# WOLF AGENT
# ============================================================

class WolfAssistant(Agent):

    def __init__(self):

        super().__init__(

            instructions=(
                AGENT_INSTRUCTION
                + """

VOICE BEHAVIOR:

The frontend controls wake-word detection.

Do not automatically start a conversation.

After "Hey Wolf":

1. Understand the user's command.
2. Select the correct tool.
3. Execute the tool.
4. Verify the result.
5. Give a short natural response.

Never claim that an action succeeded unless the
corresponding tool actually succeeded.
"""
            ),

            tools=AGENT_TOOLS,

        )


# ============================================================
# LIVEKIT ENTRYPOINT
# ============================================================

async def entrypoint(ctx):

    global AGENT_LOOP
    global LIVEKIT_READY

    AGENT_LOOP = asyncio.get_running_loop()

    logger.info(
        "Wolf agent entrypoint started."
    )

    await ctx.connect()

    LIVEKIT_READY = True

    logger.info(
        "Connected to LiveKit room: %s",
        ctx.room.name,
    )

    assistant = WolfAssistant()

    try:

        await start_voice_session(
            ctx,
            assistant,
        )

        while True:

            await asyncio.sleep(
                3600
            )

    except asyncio.CancelledError:

        logger.info(
            "Wolf voice session cancelled."
        )

    except Exception as e:

        logger.exception(
            "Voice session crashed: %s",
            e,
        )

        raise


# ============================================================
# FLASK THREAD
# ============================================================

def start_flask():

    logger.info(
        "Starting Flask backend on 127.0.0.1:5000"
    )

    app.run(

        host="127.0.0.1",

        port=5000,

        debug=False,

        use_reloader=False,

    )


# ============================================================
# MAIN
# ============================================================

def main():

    flask_thread = threading.Thread(

        target=start_flask,

        daemon=True,

    )

    flask_thread.start()

    time.sleep(
        0.5
    )

    logger.info(
        "Wolf backend is running."
    )

    logger.info(
        "Starting LiveKit worker..."
    )

    worker_options = agents.WorkerOptions(

        entrypoint_fnc=entrypoint,

    )

    if len(sys.argv) == 1:
        sys.argv.append("start")

    agents.cli.run_app(
        worker_options
    )



# ============================================================

if __name__ == "__main__":

    main()