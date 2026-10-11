# ============================================================
# WOLF AI DESKTOP ASSISTANT
# backend/registry.py
#
# Modular Tool Registry:
# - Reuses existing tools from tools.py
# - Implements clean schemas and metadata
# - Wraps execution with error handling & verification
# - Provides uniform result dictionaries:
#   {"success": bool, "message": str, "tool": str, "data": Any}
# ============================================================

import os
import sys
import inspect
import asyncio
import logging
import subprocess
import webbrowser
import urllib.parse
import threading
import random
import math
from typing import Dict, Any, Callable, Optional, List
from pathlib import Path

# Add project root to sys.path if not present
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import tools
from backend.tools_expansion import (
    get_desktop_dir,
    action_take_screenshot,
    action_analyze_screen,
    action_read_clipboard,
    action_write_clipboard,
    action_open_folder,
    action_find_file,
    action_read_file,
    action_rename_file,
    action_move_file,
    action_close_application,
    action_switch_application,
    action_search_youtube_and_play,
    action_research_topic,
    action_draft_email,
    action_draft_message,
    action_send_email,
    action_send_message,
    action_dial_phone,
)

logger = logging.getLogger("wolf.registry")


# ============================================================
# CALLABLE EXECUTION HELPER
# ============================================================

def _invoke_callable(func: Callable, **kwargs) -> Any:
    """
    Safely executes a sync or async function, correctly stripping
    LiveKit RunContext if present.
    """
    target = getattr(func, "_func", func)
    sig = inspect.signature(target)
    params = list(sig.parameters.values())

    pass_context = False
    if params:
        first_param = params[0]
        if first_param.name in ("context", "ctx") or "Context" in str(first_param.annotation):
            pass_context = True

    call_kwargs = {}
    for name, param in sig.parameters.items():
        if pass_context and name == params[0].name:
            continue
        if name in kwargs:
            call_kwargs[name] = kwargs[name]

    if inspect.iscoroutinefunction(target):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                if pass_context:
                    return pool.submit(asyncio.run, target(None, **call_kwargs)).result()
                else:
                    return pool.submit(asyncio.run, target(**call_kwargs)).result()
        else:
            if pass_context:
                return asyncio.run(target(None, **call_kwargs))
            else:
                return asyncio.run(target(**call_kwargs))
    else:
        if pass_context:
            return target(None, **call_kwargs)
        else:
            return target(**call_kwargs)


# ============================================================
# TOOL DEFINITION
# ============================================================

class ToolDefinition:
    def __init__(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        func: Callable,
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.func = func

    def to_schema(self) -> Dict[str, Any]:
        """Returns Gemini / OpenAI compatible JSON schema"""
        properties = {}
        required = []

        for param_name, param_info in self.parameters.items():
            properties[param_name] = {
                "type": param_info.get("type", "string"),
                "description": param_info.get("description", ""),
            }
            if param_info.get("required", True):
                required.append(param_name)

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }

    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Executes the tool with:
        - required parameter validation
        - unexpected parameter rejection
        - basic type validation
        - normalized success/failure results
        - safe exception handling
        """
        try:
            logger.info("Executing tool: %s with args: %s", self.name, kwargs)

            # ------------------------------------------------
            # 1. Validate parameters
            # ------------------------------------------------
            validation_error = self._validate_parameters(kwargs)

            if validation_error:
                return {
                    "success": False,
                    "ok": False,
                    "error_code": "INVALID_PARAMETERS",
                    "message": validation_error,
                    "tool": self.name,
                    "data": None,
                }

            # ------------------------------------------------
            # 2. Execute actual callable
            # ------------------------------------------------
            raw_result = _invoke_callable(self.func, **kwargs)


            # ------------------------------------------------
            # 2A. Normalize dictionary results
            # ------------------------------------------------
            if isinstance(raw_result, dict):

                # Preserve explicit failures returned by a tool.
                if (
                    raw_result.get("success") is False
                    or raw_result.get("ok") is False
                ):
                    return {
                        **raw_result,
                        "success": False,
                        "ok": False,
                        "tool": raw_result.get("tool", self.name),
                        "data": raw_result.get("data"),
                        "message": str(
                            raw_result.get(
                                "message",
                                "Tool execution failed."
                            )
                        ),
                    }

                # Preserve explicit structured successes.
                if raw_result.get("success") is True:
                    return {
                        **raw_result,
                        "success": True,
                        "ok": True,
                        "tool": raw_result.get("tool", self.name),
                    }


            # ------------------------------------------------
            # 3. Normalize tuple result
            # ------------------------------------------------
            if isinstance(raw_result, tuple):
                if len(raw_result) >= 3:
                    success, message, data = raw_result[0], raw_result[1], raw_result[2]
                    return {
                        "success": bool(success),
                        "ok": bool(success),
                        "message": str(message),
                        "tool": self.name,
                        "data": data,
                    }
                elif len(raw_result) == 2:
                    success, message = raw_result
                    return {
                        "success": bool(success),
                        "ok": bool(success),
                        "message": str(message),
                        "tool": self.name,
                        "data": kwargs,
                    }

            # ------------------------------------------------
            # 4. Normalize string result
            # ------------------------------------------------
            elif isinstance(raw_result, str):

                # Existing Wolf tools sometimes return a
                # failure message directly instead of
                # (False, message).
                failure_phrases = (
                    "i could not",
                    "i couldn't",
                    "could not",
                    "couldn't",
                    "failed",
                    "failure",
                    "unable to",
                    "cannot",
                    "can't",
                    "error",
                    "not found",
                    "not recognized",
                    "please provide",
                    "please tell me",
                )

                normalized = raw_result.strip().lower()

                is_failure = any(
                    phrase in normalized
                    for phrase in failure_phrases
                )

                return {
                    "success": not is_failure,
                    "ok": not is_failure,
                    "message": raw_result,
                    "tool": self.name,
                    "data": kwargs,
                }

            # ------------------------------------------------
            # 5. Other return values
            # ------------------------------------------------
            else:
                return {
                    "success": True,
                    "ok": True,
                    "message": (
                        str(raw_result)
                        if raw_result is not None
                        else "Done, Sir."
                    ),
                    "tool": self.name,
                    "data": raw_result,
                }

        except Exception as exc:
            logger.exception(
                "Error executing tool %s: %s",
                self.name,
                exc,
            )

            return {
                "success": False,
                "ok": False,
                "error_code": "TOOL_EXCEPTION",
                "message": (
                    f"I encountered an error executing "
                    f"{self.name}, Sir."
                ),
                "tool": self.name,
                "data": None,
            }

    def _validate_parameters(self, kwargs: Dict[str, Any]) -> Optional[str]:
        """
        Validates parameters against the tool schema.

        Phase 1 rules:
        - required parameters must be present
        - unexpected parameters are rejected
        - basic JSON-schema-like types are checked
        """

        defined = self.parameters or {}

        # ----------------------------------------------------
        # Unexpected parameters
        # ----------------------------------------------------
        unexpected = set(kwargs) - set(defined)

        if unexpected:
            names = ", ".join(sorted(unexpected))
            return (
                f"Unexpected parameter(s) for tool "
                f"'{self.name}': {names}"
            )

        # ----------------------------------------------------
        # Required parameters
        # ----------------------------------------------------
        for name, info in defined.items():
            required = info.get("required", True)

            if required and name not in kwargs:
                return (
                    f"Missing required parameter "
                    f"'{name}' for tool '{self.name}'."
                )

        # ----------------------------------------------------
        # Type validation
        # ----------------------------------------------------
        for name, value in kwargs.items():
            expected = defined[name].get("type", "string")

            if not self._matches_type(value, expected):
                return (
                    f"Invalid type for parameter '{name}': "
                    f"expected {expected}."
                )

        return None

    @staticmethod
    def _matches_type(value: Any, expected: str) -> bool:
        """
        Basic JSON-schema-compatible type validation.
        """

        if expected == "string":
            return isinstance(value, str)

        if expected == "number":
            return (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
            )
        
        if expected == "integer":
            return (
                isinstance(value, int)
                and not isinstance(value, bool)
            )

        if expected == "boolean":
            return isinstance(value, bool)

        if expected == "object":
            return isinstance(value, dict)

        if expected == "array":
            return isinstance(value, list)

        if expected == "null":
            return value is None

        # Unknown schema type: reject rather than silently
        # accepting invalid data.
        return False


# ============================================================
# TOOL REGISTRY CLASS
# ============================================================

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        func: Callable,
    ):
        tool = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            func=func,
        )
        self._tools[name] = tool
        logger.debug("Registered tool: %s", name)

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def list_tools(self) -> List[ToolDefinition]:
        return list(self._tools.values())

    def get_schemas(self) -> List[Dict[str, Any]]:
        return [tool.to_schema() for tool in self._tools.values()]

    def execute(self, *args, **kwargs) -> Dict[str, Any]:
        if args:
            tool_name = args[0]
        else:
            tool_name = kwargs.pop("tool_name", kwargs.pop("name", None))
        tool = self.get(tool_name)
        if not tool:
            logger.warning("Tool not found in registry: %s", tool_name)
            return {
                "success": False,
                "message": f"Tool '{tool_name}' is not recognized, Sir.",
                "tool": tool_name,
                "data": None,
            }
        return tool.execute(**kwargs)


# ============================================================
# LOCAL WINDOWS ACTION HELPERS (REUSED FROM AGENT.PY)
# ============================================================

def _safe_open_url(url: str) -> bool:
    """
    Robust URL opener for Windows:
    Uses os.startfile first (guarantees default browser launch and foreground activation).
    Falls back to webbrowser.open.
    """
    url = (url or "").strip()
    if not url:
        return False
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        if sys.platform == "win32" and hasattr(os, "startfile"):
            try:
                os.startfile(url)
                logger.info("Opened URL via os.startfile: %s", url)
                return True
            except Exception as e:
                logger.debug("os.startfile failed (%s), using webbrowser", e)
        success = webbrowser.open(url, new=2)
        logger.info("Opened URL via webbrowser.open: %s (result=%s)", url, success)
        return True
    except Exception as e:
        logger.error("Failed to open URL %s: %s", url, e)
        return False


def action_open_google():
    try:
        url = "https://www.google.com/"
        success = _safe_open_url(url)
        if not success:
            return False, "Google could not be opened, Sir."
        return True, "Google has been opened, Sir."
    except Exception as e:
        return False, f"I could not open Google, Sir. {e}"


def action_open_youtube():
    try:
        url = "https://www.youtube.com/"
        success = _safe_open_url(url)
        if not success:
            return False, "YouTube could not be opened, Sir."
        return True, "YouTube has been opened, Sir."
    except Exception as e:
        return False, f"I could not open YouTube, Sir. {e}"


def action_open_gmail():
    try:
        url = "https://mail.google.com/"
        success = _safe_open_url(url)
        if not success:
            return False, "Gmail could not be opened, Sir."
        return True, "Gmail has been opened, Sir."
    except Exception as e:
        return False, f"I could not open Gmail, Sir. {e}"


def action_search_google(query: str):
    query = (query or "").strip()
    if not query:
        return False, "Please tell me what you want to search for, Sir."
    try:
        url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)
        success = _safe_open_url(url)
        if not success:
            return False, f"I could not open the browser to search Google for {query}, Sir."
        return True, f"I searched Google for {query}, Sir."
    except Exception as e:
        return False, f"Google search failed, Sir. {e}"


def action_search_youtube(query: str):
    query = (query or "").strip()
    if not query:
        return False, "Please tell me what to search on YouTube, Sir."
    try:
        url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
        success = _safe_open_url(url)
        if not success:
            return False, f"I could not open the browser to search YouTube for {query}, Sir."
        return True, f"I searched YouTube for {query}, Sir."
    except Exception as e:
        return False, f"YouTube search failed, Sir. {e}"


def action_play_youtube(query: str):
    query = (query or "").strip()
    if not query:
        return False, "Please tell me what you want to play, Sir."
    res = action_search_youtube_and_play(query)
    return res.get("success", False), res.get("message", ""), res.get("data")


def action_open_application(application: str):
    application = (application or "").strip().lower()
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
    executable = aliases.get(application)
    if not executable:
        return False, f"I don't have a Windows launcher configured for {application}, Sir."

    try:
        subprocess.Popen([executable], shell=False)
        return True, f"{application.title()} has been opened, Sir."
    except Exception as e:
        return False, f"I could not open {application}, Sir. {e}"


def action_open_file(path: str):
    path = (path or "").strip()
    if not path:
        return False, "Please provide a file path, Sir."
    try:
        path = os.path.expandvars(os.path.expanduser(path))
        if not os.path.exists(path):
            return False, f"I could not find {path}, Sir."
        os.startfile(path)
        return True, f"I opened {path}, Sir."
    except Exception as e:
        return False, f"I could not open that file, Sir. {e}"


def action_create_project_folder(name: str):
    name = (name or "").strip()
    if not name:
        return False, "Please tell me the folder name, Sir."
    try:
        safe_name = "".join(c for c in name if c.isalnum() or c in (" ", "_", "-")).strip()
        if not safe_name:
            return False, "That folder name is not valid, Sir."

        active_desktop = get_desktop_dir()
        project_root = active_desktop / "Wolf Projects"
        project_root.mkdir(parents=True, exist_ok=True)
        folder = project_root / safe_name
        folder.mkdir(parents=True, exist_ok=True)

        std_desktop = Path.home() / "Desktop"
        if std_desktop.resolve() != active_desktop.resolve():
            try:
                (std_desktop / "Wolf Projects" / safe_name).mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

        # Return 3-tuple so verifier and multi-step executor get the path
        return True, f"The folder '{safe_name}' has been created on your Desktop under Wolf Projects, Sir.", {"path": str(folder)}
    except Exception as e:
        return False, f"I could not create the folder, Sir. {e}"


def action_create_file(folder_name: str, file_name: str, content: str = ""):
    """Create a file inside an existing Wolf Projects folder."""
    folder_name = (folder_name or "").strip()
    file_name = (file_name or "").strip()

    if not folder_name:
        return False, "Please tell me the folder name, Sir."
    if not file_name:
        return False, "Please tell me the file name, Sir."

    try:
        safe_folder = "".join(c for c in folder_name if c.isalnum() or c in (" ", "_", "-")).strip()
        safe_file = "".join(c for c in file_name if c.isalnum() or c in (" ", "_", "-", ".")).strip()

        if not safe_folder:
            return False, "That folder name is not valid, Sir."
        if not safe_file:
            return False, "That file name is not valid, Sir."

        active_desktop = get_desktop_dir()
        project_root = active_desktop / "Wolf Projects"
        folder = project_root / safe_folder
        folder.mkdir(parents=True, exist_ok=True)

        file_path = folder / safe_file
        file_path.write_text(content, encoding="utf-8")

        std_desktop = Path.home() / "Desktop"
        if std_desktop.resolve() != active_desktop.resolve():
            try:
                mirror_folder = std_desktop / "Wolf Projects" / safe_folder
                mirror_folder.mkdir(parents=True, exist_ok=True)
                (mirror_folder / safe_file).write_text(content, encoding="utf-8")
            except Exception:
                pass

        return True, f"I created '{safe_file}' inside '{safe_folder}', Sir.", {"path": str(file_path)}
    except Exception as e:
        return False, f"I could not create the file, Sir. {e}"


def action_set_timer(minutes: float):
    try:
        minutes = float(minutes)
        if minutes <= 0:
            return False, "The timer must be greater than zero, Sir."

        seconds = minutes * 60

        def timer_finished():
            try:
                import winsound
                for _ in range(3):
                    winsound.Beep(1000, 500)
            except Exception:
                print(f"\n[Wolf] Timer finished: {minutes} minutes")

        timer = threading.Timer(seconds, timer_finished)
        timer.daemon = True
        timer.start()
        return True, f"Timer set for {minutes:g} minutes, Sir."
    except Exception as e:
        return False, f"I could not set the timer, Sir. {e}"


def action_motivate_user():
    messages = [
        "You've got this, Sir. One focused step at a time.",
        "Keep going. Progress comes from consistency, Sir.",
        "Don't wait for perfect. Build, test, improve, repeat.",
        "Your future self will thank you for the work you do today.",
        "Stay focused, Sir. You're closer than you think.",
    ]
    return True, random.choice(messages)


# ============================================================
# INSTANTIATE & REGISTER ALL EXISTING TOOLS
# ============================================================

def create_default_registry() -> ToolRegistry:
    registry = ToolRegistry()

    # 1. Open Application
    registry.register(
        name="open_application",
        description="Launch a Windows application such as Notepad, Calculator, Paint, Command Prompt, PowerShell, or File Explorer.",
        parameters={
            "application": {
                "type": "string",
                "description": "The application to launch: notepad, calculator, paint, cmd, powershell, explorer.",
                "required": True,
            }
        },
        func=action_open_application,
    )

    # 2. Search Web (DuckDuckGo + Wikipedia from tools.py)
    registry.register(
        name="search_web",
        description="Search the web for up-to-date information, facts, research, news, or general knowledge.",
        parameters={
            "query": {
                "type": "string",
                "description": "The search query or factual question to look up.",
                "required": True,
            }
        },
        func=tools.search_web,
    )

    # 3. Get Weather (from tools.py)
    registry.register(
        name="get_weather",
        description="Get current weather conditions and temperature for a specific city.",
        parameters={
            "city": {
                "type": "string",
                "description": "City name, e.g. London, Tokyo, New York, Delhi.",
                "required": True,
            }
        },
        func=tools.get_weather,
    )

    # 4. Search Google
    registry.register(
        name="search_google",
        description="Search Google and display search results in the user's web browser.",
        parameters={
            "query": {
                "type": "string",
                "description": "The search query to search on Google.",
                "required": True,
            }
        },
        func=action_search_google,
    )

    # 5. Open Google
    registry.register(
        name="open_google",
        description="Open the Google homepage in the default browser.",
        parameters={},
        func=action_open_google,
    )

    # 6. Search YouTube
    registry.register(
        name="search_youtube",
        description="Search YouTube for videos and open the results in the web browser.",
        parameters={
            "query": {
                "type": "string",
                "description": "The video search term for YouTube.",
                "required": True,
            }
        },
        func=action_search_youtube,
    )

    # 7. Play YouTube
    registry.register(
        name="play_youtube",
        description="Search and play a video or music track on YouTube in the browser.",
        parameters={
            "query": {
                "type": "string",
                "description": "The song, video, or content to play on YouTube.",
                "required": True,
            }
        },
        func=action_play_youtube,
    )

    # 8. Open YouTube Homepage
    registry.register(
        name="open_youtube",
        description="Open the YouTube homepage in the default browser.",
        parameters={},
        func=action_open_youtube,
    )

    # 9. Open Gmail
    registry.register(
        name="open_gmail",
        description="Open Gmail in the default browser.",
        parameters={},
        func=action_open_gmail,
    )

    # 10. Open Website URL (from tools.py)
    registry.register(
        name="open_website",
        description="Open a specified website or URL in the default web browser.",
        parameters={
            "url": {
                "type": "string",
                "description": "The URL or domain to open, e.g. https://github.com or reddit.com.",
                "required": True,
            }
        },
        func=tools.open_website,
    )

    # 11. Open File Explorer (from tools.py)
    registry.register(
        name="open_file_explorer",
        description="Open Windows File Explorer to browse local files and drives.",
        parameters={},
        func=tools.open_file_explorer,
    )

    # 12. Open Local File
    registry.register(
        name="open_file",
        description="Open a file from the local Windows filesystem using its default application.",
        parameters={
            "path": {
                "type": "string",
                "description": "Path to the local file to open.",
                "required": True,
            }
        },
        func=action_open_file,
    )

    # 13. Create Project Folder
    registry.register(
        name="create_project_folder",
        description="Create a new project folder on the Desktop under 'Wolf Projects'.",
        parameters={
            "name": {
                "type": "string",
                "description": "Name for the project folder.",
                "required": True,
            }
        },
        func=action_create_project_folder,
    )

    # 13b. Create File inside a Wolf Projects folder
    registry.register(
        name="create_file",
        description="Create a new file inside a folder under 'Wolf Projects' on the Desktop. Use this when the user asks to create a file or text file inside a folder.",
        parameters={
            "folder_name": {
                "type": "string",
                "description": "Name of the parent folder under Wolf Projects.",
                "required": True,
            },
            "file_name": {
                "type": "string",
                "description": "Name of the file to create, e.g. hello.txt, notes.md.",
                "required": True,
            },
            "content": {
                "type": "string",
                "description": "Optional initial content to write into the file.",
                "required": False,
            },
        },
        func=action_create_file,
    )

    # 14. Set Timer
    registry.register(
        name="set_timer",
        description="Set a countdown timer for a specified number of minutes with an audio alarm.",
        parameters={
            "minutes": {
                "type": "number",
                "description": "Number of minutes for the countdown.",
                "required": True,
            }
        },
        func=action_set_timer,
    )

    # 15. Motivate User
    registry.register(
        name="motivate_user",
        description="Speak an inspiring butler-style motivational quote to encourage the user.",
        parameters={},
        func=action_motivate_user,
    )

    # 16. Play Local Music (from tools.py)
    registry.register(
        name="play_music",
        description="Play a local audio file from disk.",
        parameters={
            "file_path": {
                "type": "string",
                "description": "Path to the local audio file to play.",
                "required": True,
            }
        },
        func=tools.play_music,
    )

    # 17. Take Screenshot
    registry.register(
        name="take_screenshot",
        description="Capture a screenshot of the user's screen and save it to Wolf Projects/Screenshots.",
        parameters={
            "filename": {
                "type": "string",
                "description": "Optional custom filename for the screenshot image.",
                "required": False,
            }
        },
        func=action_take_screenshot,
    )

    # 18. Analyze Screen
    registry.register(
        name="analyze_screen",
        description="Capture the screen and analyze what is visible (read text, explain errors, identify active windows).",
        parameters={
            "prompt": {
                "type": "string",
                "description": "Question or prompt regarding the screen contents or error.",
                "required": False,
            }
        },
        func=action_analyze_screen,
    )

    # 19. Read Clipboard
    registry.register(
        name="read_clipboard",
        description="Read the current text copied to the Windows clipboard.",
        parameters={},
        func=action_read_clipboard,
    )

    # 20. Write Clipboard
    registry.register(
        name="write_clipboard",
        description="Copy or write specified text into the Windows clipboard.",
        parameters={
            "text": {
                "type": "string",
                "description": "The text to copy to the clipboard.",
                "required": True,
            }
        },
        func=action_write_clipboard,
    )

    # 21. Open Folder
    registry.register(
        name="open_folder",
        description="Open a specific folder or common directory (e.g. Desktop, Downloads, Documents, Wolf Projects) in File Explorer.",
        parameters={
            "folder_path": {
                "type": "string",
                "description": "Folder name or path to open.",
                "required": True,
            }
        },
        func=action_open_folder,
    )

    # 22. Find File
    registry.register(
        name="find_file",
        description="Search for a file by name across user directories (Desktop, Downloads, Documents, Wolf Projects).",
        parameters={
            "filename": {
                "type": "string",
                "description": "Name or keyword of the file to search.",
                "required": True,
            },
            "search_dir": {
                "type": "string",
                "description": "Optional directory to limit the search.",
                "required": False,
            },
        },
        func=action_find_file,
    )

    # 23. Read File
    registry.register(
        name="read_file",
        description="Read content from a text file on disk.",
        parameters={
            "file_path": {
                "type": "string",
                "description": "Path or filename to read.",
                "required": True,
            },
            "max_lines": {
                "type": "number",
                "description": "Maximum number of lines to read.",
                "required": False,
            },
        },
        func=action_read_file,
    )

    # 24. Rename File
    registry.register(
        name="rename_file",
        description="Rename a file on disk.",
        parameters={
            "old_path": {
                "type": "string",
                "description": "Current file path or name.",
                "required": True,
            },
            "new_name": {
                "type": "string",
                "description": "New file name.",
                "required": True,
            },
        },
        func=action_rename_file,
    )

    # 25. Move File
    registry.register(
        name="move_file",
        description="Move a file to a target destination folder.",
        parameters={
            "source_path": {
                "type": "string",
                "description": "Source file path.",
                "required": True,
            },
            "destination_folder": {
                "type": "string",
                "description": "Destination folder path.",
                "required": True,
            },
        },
        func=action_move_file,
    )

    # 26. Close Application
    registry.register(
        name="close_application",
        description="Close an active application or process by name (e.g. calculator, notepad, paint, chrome).",
        parameters={
            "application_name": {
                "type": "string",
                "description": "Application name to terminate.",
                "required": True,
            }
        },
        func=action_close_application,
    )

    # 27. Switch Application
    registry.register(
        name="switch_application",
        description="Bring an existing open window or application to the foreground.",
        parameters={
            "application_name": {
                "type": "string",
                "description": "Application title or name to switch to.",
                "required": True,
            }
        },
        func=action_switch_application,
    )

    # 28. Search YouTube and Play
    registry.register(
        name="search_youtube_and_play",
        description="Search YouTube for any song/video query and automatically play the first video result.",
        parameters={
            "query": {
                "type": "string",
                "description": "Song, artist, or video to play on YouTube.",
                "required": True,
            }
        },
        func=action_search_youtube_and_play,
    )

    # 29. Research Topic
    registry.register(
        name="research_topic",
        description="Conduct comprehensive web research on a topic, synthesize key points, and provide citations.",
        parameters={
            "query": {
                "type": "string",
                "description": "Research question or topic.",
                "required": True,
            },
            "max_results": {
                "type": "number",
                "description": "Maximum web sources to analyze.",
                "required": False,
            },
        },
        func=action_research_topic,
    )

    # 30. Draft Email
    registry.register(
        name="draft_email",
        description="Draft an email for a recipient with subject and body without sending it.",
        parameters={
            "recipient": {
                "type": "string",
                "description": "Name or email of recipient.",
                "required": True,
            },
            "subject": {
                "type": "string",
                "description": "Email subject line.",
                "required": True,
            },
            "purpose": {
                "type": "string",
                "description": "Purpose or contents of the email.",
                "required": True,
            },
        },
        func=action_draft_email,
    )

    # 31. Draft Message
    registry.register(
        name="draft_message",
        description="Draft a message for a recipient without sending it.",
        parameters={
            "recipient": {
                "type": "string",
                "description": "Name of the person to message.",
                "required": True,
            },
            "message": {
                "type": "string",
                "description": "Content of the message.",
                "required": True,
            },
            "platform": {
                "type": "string",
                "description": "Messaging platform (default, WhatsApp, Telegram).",
                "required": False,
            },
        },
        func=action_draft_message,
    )

    # 32. Send Email
    registry.register(
        name="send_email",
        description="Send an email to a recipient. (High-impact action: requires user confirmation).",
        parameters={
            "recipient": {
                "type": "string",
                "description": "Recipient address or name.",
                "required": True,
            },
            "subject": {
                "type": "string",
                "description": "Subject of the email.",
                "required": True,
            },
            "body": {
                "type": "string",
                "description": "Body text of the email.",
                "required": True,
            },
        },
        func=action_send_email,
    )

    # 33. Send Message
    registry.register(
        name="send_message",
        description="Send a message to a recipient. (High-impact action: requires user confirmation).",
        parameters={
            "recipient": {
                "type": "string",
                "description": "Recipient name.",
                "required": True,
            },
            "message": {
                "type": "string",
                "description": "Message text.",
                "required": True,
            },
            "platform": {
                "type": "string",
                "description": "Platform to send on.",
                "required": False,
            },
        },
        func=action_send_message,
    )

    # 34. Dial Phone
    registry.register(
        name="dial_phone",
        description="Dial or call a phone number or contact. (High-impact action: requires user confirmation).",
        parameters={
            "phone_number": {
                "type": "string",
                "description": "Phone number or contact to call.",
                "required": True,
            }
        },
        func=action_dial_phone,
    )

    return registry


# Singleton registry instance
tool_registry = create_default_registry()
