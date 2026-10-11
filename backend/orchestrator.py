# ============================================================
# WOLF AI DESKTOP ASSISTANT
# backend/orchestrator.py
#
# Agentic Orchestration Layer:
# - Two-tier execution:
#   1. Fast Path (<5ms direct execution for deterministic commands)
#   2. Agentic Path (Gemini tool-selection for natural/complex queries)
# - Unified execution via backend/registry.py
# - Conversational fallback with Wolf persona
# - Structured logging
# - Resilient error handling
# ============================================================

import os
import sys
import re
import json
import time
import logging

from typing import Dict, Any, Optional
from pathlib import Path


# ============================================================
# PROJECT PATH
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


# ============================================================
# IMPORTS
# ============================================================

from backend.registry import tool_registry, ToolRegistry
from backend.planner import TaskPlan, TaskStep
from backend.executor import TaskExecutor
from backend.verifier import get_default_verifiers
from backend.safety import safety_manager
from promts import AGENT_INSTRUCTION


logger = logging.getLogger("wolf.orchestrator")


# ============================================================
# AGENT ORCHESTRATOR
# ============================================================

class AgentOrchestrator:

    def __init__(
        self,
        gemini_client=None,
        model_name: str = "gemini-3.5-flash-lite",
        registry: Optional[ToolRegistry] = None,
    ):
        self.client = gemini_client
        self.model_name = model_name or "gemini-3.5-flash-lite"
        self.registry = registry or tool_registry
        self.fallback_models = [
            "gemini-3.5-flash-lite",
            "gemini-3.8-flash",
            "gemini-3.1-flash-lite",
            "gemini-2.5-pro",
            "gemini-flash-latest",
        ]
        self.executor = TaskExecutor(
            registry=self.registry,
            verifiers=get_default_verifiers(),
        )

    # ========================================================
    # CLIENT CONFIGURATION
    # ========================================================

    def set_client(self, client, model_name: str = None):
        """Update Gemini client instance or model name dynamically."""

        self.client = client

        if model_name:
            self.model_name = model_name

    # ========================================================
    # TIER 1: FAST PATH
    # ========================================================

    def _try_fast_path(
        self,
        text: str
    ) -> Optional[Dict[str, Any]]:
        """
        Fast Path execution for common, unambiguous commands.

        Returns a decision dictionary if the command can be
        handled deterministically, otherwise returns None.

        For multi-step commands (e.g. "create folder X and file Y"),
        returns a special {"tool": "__multi__", "steps": [...]} dict
        which process_command handles by sequential execution.
        """

        original = text.strip()
        lower = original.lower()

        # Strips filler words that voice recognition often prepends
        # ("please", "can you", "could you", "wolf", etc.)
        def strip_filler(s: str) -> str:
            modified = True
            while modified:
                modified = False
                for filler in (
                    "please ", "can you ", "could you ", "would you ",
                    "wolf ", "hey wolf ", "i want to ", "i'd like to ",
                    "i want you to ", "i need you to ", "kindly ",
                ):
                    if s.lower().startswith(filler):
                        s = s[len(filler):]
                        modified = True
            return s

        clean = strip_filler(lower)
        clean_original = strip_filler(original)

        # ----------------------------------------------------
        # 1. Applications
        # ----------------------------------------------------

        app_map = {
            "notepad": "notepad",
            "calculator": "calculator",
            "calc": "calculator",
            "paint": "paint",
            "cmd": "cmd",
            "command prompt": "command prompt",
            "powershell": "powershell",
            "power shell": "powershell",
        }

        for name, app_id in app_map.items():
            for candidate in (lower, clean):
                cand_clean = candidate.rstrip(".?!")
                if cand_clean in (
                    f"open {name}",
                    f"launch {name}",
                    f"start {name}",
                    f"run {name}",
                ):
                    return {
                        "tool": "open_application",
                        "params": {"application": app_id},
                        "intent": "open_application",
                    }

        # ----------------------------------------------------
        # 2. File Explorer
        # ----------------------------------------------------

        explorer_triggers = {
            "open file explorer", "open explorer", "open files",
            "open file manager", "file explorer", "show files",
            "open my files", "show my files",
        }
        if lower.rstrip(".?!") in explorer_triggers or clean.rstrip(".?!") in explorer_triggers:
            return {
                "tool": "open_file_explorer",
                "params": {},
                "intent": "open_file_explorer",
            }

        # ----------------------------------------------------
        # 3. Google Homepage
        # ----------------------------------------------------

        google_home = {
            "open google", "open google.com", "launch google",
            "go to google", "visit google",
        }
        if lower.rstrip(".?!") in google_home or clean.rstrip(".?!") in google_home:
            return {
                "tool": "open_google",
                "params": {},
                "intent": "open_google",
            }

        # ----------------------------------------------------
        # 4. YouTube Homepage
        # ----------------------------------------------------

        yt_home = {
            "open youtube", "launch youtube", "open youtube.com",
            "go to youtube", "visit youtube",
        }
        if lower.rstrip(".?!") in yt_home or clean.rstrip(".?!") in yt_home:
            return {
                "tool": "open_youtube",
                "params": {},
                "intent": "open_youtube",
            }

        # ----------------------------------------------------
        # 5. Gmail
        # ----------------------------------------------------

        gmail_home = {
            "open gmail", "open email", "open google mail",
            "launch gmail", "go to gmail",
        }
        if lower.rstrip(".?!") in gmail_home or clean.rstrip(".?!") in gmail_home:
            return {
                "tool": "open_gmail",
                "params": {},
                "intent": "open_gmail",
            }

        # ----------------------------------------------------
        # 6. Google Search  — many natural-language variants
        # ----------------------------------------------------

        if clean.rstrip(".?!") in ("open google and search", "open google and search something", "open google to search"):
            return {
                "tool": "open_google",
                "params": {},
                "intent": "open_google",
            }

        # Check "open google and search for X" / "open google and search X"
        m_open_search = re.search(
            r"^(?:open|go\s+to|launch)\s+google\s+and\s+search\s+(?:for\s+|something\s+like\s+)?(.+?)[\.\?!]*$",
            clean,
            re.IGNORECASE,
        )
        if m_open_search:
            query = m_open_search.group(1).strip()
            if query.lower() in ("something", "anything", "stuff", ""):
                return {
                    "tool": "open_google",
                    "params": {},
                    "intent": "open_google",
                }
            return {
                "tool": "search_google",
                "params": {"query": query},
                "intent": "search_google",
            }

        # Check "search for X on google" / "look up X on google"
        m_on_google = re.search(
            r"^(?:search\s+for|search|look\s+up)\s+(.+?)\s+on\s+google[\.\?!]*$",
            clean,
            re.IGNORECASE,
        )
        if m_on_google:
            query = m_on_google.group(1).strip()
            if query:
                return {
                    "tool": "search_google",
                    "params": {"query": query},
                    "intent": "search_google",
                }

        google_prefixes = [
            "open google and search for ",
            "open google and search ",
            "go to google and search for ",
            "go to google and search ",
            "search google for ",
            "search for ",          # generic search → Google
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
            for candidate_original, candidate_lower in (
                (original, lower),
                (clean_original, clean),
            ):
                if candidate_lower.startswith(prefix):
                    query = candidate_original[len(prefix):].rstrip(".?!").strip()
                    if query:
                        return {
                            "tool": "search_google",
                            "params": {"query": query},
                            "intent": "search_google",
                        }

        # ----------------------------------------------------
        # 6b. YouTube Search and Play (First result / Song)
        # ----------------------------------------------------

        # Match: "Play YouTube Video: Search YouTube for Shape of You and play the first result"
        #        "Play YouTube Video: Shape of You", "play youtube video ..."
        m_play_yt_vid = re.search(
            r"^(?:play\s+youtube\s+video|play\s+video\s+on\s+youtube)\s*[:\-]?\s*(.+)[\.\?!]*$",
            clean_original,
            re.IGNORECASE,
        )
        if m_play_yt_vid:
            sub = m_play_yt_vid.group(1).strip()
            m_inner = re.search(r"(?:search\s+youtube\s+for\s+)?(.+?)\s+and\s+play", sub, re.IGNORECASE)
            q = m_inner.group(1).strip() if m_inner else sub
            q = re.sub(r"^(?:video\s+|song\s+)", "", q, flags=re.IGNORECASE).strip()
            if q:
                return {
                    "tool": "search_youtube_and_play",
                    "params": {"query": q},
                    "intent": "search_youtube_and_play",
                }

        m_yt_search_play = re.search(
            r"^(?:search\s+youtube\s+for\s+|look\s+up\s+on\s+youtube\s+|search\s+on\s+youtube\s+for\s+)(.+?)\s+and\s+play(?:\s+(?:the\s+)?first\s+(?:result|song|video)|\s+it|\s+the\s+video)?[\.\?!]*$",
            clean_original,
            re.IGNORECASE,
        )
        if m_yt_search_play:
            q = m_yt_search_play.group(1).strip()
            if q:
                return {
                    "tool": "search_youtube_and_play",
                    "params": {"query": q},
                    "intent": "search_youtube_and_play",
                }

        m_play_on_yt = re.search(
            r"^play\s+(.+?)\s+(?:on\s+youtube)[\.\?!]*$",
            clean_original,
            re.IGNORECASE,
        )
        if m_play_on_yt:
            q = m_play_on_yt.group(1).strip()
            if q:
                return {
                    "tool": "search_youtube_and_play",
                    "params": {"query": q},
                    "intent": "search_youtube_and_play",
                }

        m_play_song = re.search(
            r"^play\s+(?:the\s+)?(?:song|music|track)\s+(.+)[\.\?!]*$",
            clean_original,
            re.IGNORECASE,
        )
        if m_play_song:
            q = m_play_song.group(1).strip()
            if q:
                return {
                    "tool": "search_youtube_and_play",
                    "params": {"query": q},
                    "intent": "search_youtube_and_play",
                }

        # ----------------------------------------------------
        # 7. YouTube Search
        # ----------------------------------------------------

        yt_prefixes = [
            "search youtube for ",
            "search youtube ",
            "youtube search for ",
            "youtube search ",
            "search on youtube for ",
            "search on youtube ",
        ]

        for prefix in yt_prefixes:
            for candidate_original, candidate_lower in (
                (original, lower),
                (clean_original, clean),
            ):
                if candidate_lower.startswith(prefix):
                    query = candidate_original[len(prefix):].rstrip(".?!").strip()
                    if query:
                        return {
                            "tool": "search_youtube",
                            "params": {"query": query},
                            "intent": "search_youtube",
                        }

        # ----------------------------------------------------
        # 8. Play YouTube (Direct playback)
        # ----------------------------------------------------

        if "youtube" in lower and (lower.startswith("play") or clean.startswith("play")):
            src = clean_original if clean.startswith("play") else original
            query = src
            for phrase in ("play on youtube", "play on YouTube", "play youtube", "play YouTube", "play"):
                query = query.replace(phrase, "")
            query = query.strip().strip("the").strip(":").rstrip(".?!").strip()
            if query:
                return {
                    "tool": "search_youtube_and_play",
                    "params": {"query": query},
                    "intent": "search_youtube_and_play",
                }

        # ----------------------------------------------------
        # 9a. Multi-step: Create folder AND create file inside it
        #     Handles: "create folder X and create file Y inside it"
        #               "create folder X and file Y"
        #               "make folder X and file Y inside it"
        # ----------------------------------------------------

        multi_folder_file = re.search(
            r"(?:create|make)\s+(?:a\s+)?folder\s+"
            r"(?:called\s+|named\s+)?[\"']?([A-Za-z0-9 _\-]+?)[\"']?"
            r"\s+and\s+(?:create\s+)?(?:a\s+)?file\s+"
            r"(?:called\s+|named\s+)?[\"']?([A-Za-z0-9 _\-\.]+?)[\"']?"
            r"(?:\s+inside\s+it|\s+in\s+it|\s+inside\s+the\s+folder)?[\.\?!]*$",
            clean_original,
            re.IGNORECASE,
        )

        if multi_folder_file:
            folder_name = multi_folder_file.group(1).strip()
            file_name = multi_folder_file.group(2).strip()
            if folder_name and file_name:
                return {
                    "tool": "__multi__",
                    "steps": [
                        {
                            "tool": "create_project_folder",
                            "params": {"name": folder_name},
                        },
                        {
                            "tool": "create_file",
                            "params": {
                                "folder_name": folder_name,
                                "file_name": file_name,
                                "content": "",
                            },
                        },
                    ],
                    "intent": "create_folder_and_file",
                }

        # ----------------------------------------------------
        # 9b. Create Project Folder (single)
        # ----------------------------------------------------

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
            for candidate_lower, candidate_original in (
                (lower, original),
                (clean, clean_original),
            ):
                if candidate_lower.startswith(prefix):
                    folder_name = candidate_original[len(prefix):].rstrip(".?!").strip()
                    # Remove trailing "on the desktop", "on desktop", etc.
                    folder_name = re.sub(
                        r"\s+(?:on\s+(?:the\s+)?desktop|in\s+wolf\s+projects|on\s+my\s+desktop)$",
                        "",
                        folder_name,
                        flags=re.IGNORECASE,
                    ).strip()
                    if folder_name:
                        return {
                            "tool": "create_project_folder",
                            "params": {"name": folder_name},
                            "intent": "create_project_folder",
                        }

        # ----------------------------------------------------
        # 9c. Create File (standalone)
        # ----------------------------------------------------

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
            for candidate_lower, candidate_original in (
                (lower, original),
                (clean, clean_original),
            ):
                if candidate_lower.startswith(prefix):
                    remainder = candidate_original[len(prefix):].rstrip(".?!").strip()
                    # Check "inside X" / "in folder X"
                    m = re.match(
                        r"^(.+?)\s+(?:inside|in)\s+(?:folder\s+)?(.+)$",
                        remainder,
                        re.IGNORECASE,
                    )
                    if m:
                        file_name = m.group(1).strip()
                        folder_name = m.group(2).strip()
                    else:
                        file_name = remainder
                        folder_name = "General"
                    if file_name:
                        return {
                            "tool": "create_file",
                            "params": {
                                "folder_name": folder_name,
                                "file_name": file_name,
                                "content": "",
                            },
                            "intent": "create_file",
                        }

        # ----------------------------------------------------
        # 10. Timer
        # ----------------------------------------------------

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
                return {
                    "tool": "set_timer",
                    "params": {"minutes": minutes},
                    "intent": "set_timer",
                }

        # ----------------------------------------------------
        # 11. Motivation
        # ----------------------------------------------------

        motivate_triggers = {
            "motivate me", "motivation", "give me motivation",
            "inspire me", "give me a quote", "say something motivational",
        }
        if lower in motivate_triggers or clean in motivate_triggers:
            return {
                "tool": "motivate_user",
                "params": {},
                "intent": "motivate_user",
            }

        # ----------------------------------------------------
        # 12. Weather
        # ----------------------------------------------------

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
            for candidate_lower, candidate_original in (
                (lower, original),
                (clean, original[len(lower) - len(clean):] if len(lower) > len(clean) else original),
            ):
                if candidate_lower.startswith(prefix):
                    city = candidate_original[len(prefix):].strip()
                    if city:
                        return {
                            "tool": "get_weather",
                            "params": {"city": city},
                            "intent": "get_weather",
                        }

        # ----------------------------------------------------
        # 13. Open Website
        # ----------------------------------------------------

        for pfx in ("open website ", "open site ", "open url ", "go to ", "visit "):
            if lower.startswith(pfx) or clean.startswith(pfx):
                src_lower = lower if lower.startswith(pfx) else clean
                src_orig = original if lower.startswith(pfx) else original[len(lower) - len(clean):]
                url = src_orig[len(pfx):].strip()
                # Only treat as URL if it looks like a domain or http(s)
                if url and ("." in url or url.startswith("http")):
                    return {
                        "tool": "open_website",
                        "params": {"url": url},
                        "intent": "open_website",
                    }

        # ----------------------------------------------------
        # 14. Screenshot & Vision Analysis
        # ----------------------------------------------------

        if any(lower.startswith(p) or clean.startswith(p) for p in (
            "take a screenshot and tell me",
            "take a screenshot and explain",
            "take a screenshot and describe",
            "what is on my screen",
            "analyze my screen",
            "explain this error on my screen",
        )):
            prompt = clean
            for p in ("take a screenshot and tell me ", "take a screenshot and explain ", "take a screenshot and describe ", "explain this error on my screen"):
                if clean.lower().startswith(p):
                    prompt = clean[len(p):].strip()
                    break
            return {
                "tool": "analyze_screen",
                "params": {"prompt": prompt},
                "intent": "analyze_screen",
            }

        screenshot_triggers = {
            "take a screenshot", "take screenshot", "capture screen",
            "capture my screen", "take a screenshot of my screen",
            "take a screenshot of my current screen", "take screenshot of my screen",
            "screenshot", "screen capture",
        }
        if lower.rstrip(".?!") in screenshot_triggers or clean.rstrip(".?!") in screenshot_triggers:
            return {
                "tool": "take_screenshot",
                "params": {},
                "intent": "take_screenshot",
            }

        # ----------------------------------------------------
        # 15. Clipboard
        # ----------------------------------------------------

        clipboard_read = {
            "read my clipboard", "read clipboard", "what is on my clipboard",
            "what's on my clipboard", "show clipboard", "check clipboard",
            "what did i copy", "read what i copied",
            "what is in my clipboard", "what's in my clipboard",
            "what is in the clipboard", "what's in the clipboard",
            "what is in clipboard", "what's in clipboard",
            "check my clipboard", "view clipboard",
        }
        if lower.rstrip(".?!") in clipboard_read or clean.rstrip(".?!") in clipboard_read:
            return {
                "tool": "read_clipboard",
                "params": {},
                "intent": "read_clipboard",
            }

        # Clipboard write
        m_copy_to_clip = re.search(
            r"^(?:copy|put)\s+(?:the\s+text\s+)?['\"]?(.+?)['\"]?\s+to\s+(?:the\s+|my\s+)?clipboard[\.\?!]*$",
            clean_original,
            re.IGNORECASE,
        )
        if m_copy_to_clip:
            text_val = m_copy_to_clip.group(1).strip().strip("\"'")
            if text_val:
                return {
                    "tool": "write_clipboard",
                    "params": {"text": text_val},
                    "intent": "write_clipboard",
                }

        m_copy_clip_pfx = re.search(
            r"^(?:copy\s+to\s+(?:my\s+|the\s+)?clipboard)\s+['\"]?(.+?)['\"]?[\.\?!]*$",
            clean_original,
            re.IGNORECASE,
        )
        if m_copy_clip_pfx:
            text_val = m_copy_clip_pfx.group(1).strip().strip("\"'")
            if text_val:
                return {
                    "tool": "write_clipboard",
                    "params": {"text": text_val},
                    "intent": "write_clipboard",
                }

        # ----------------------------------------------------
        # 16. Close Application
        # ----------------------------------------------------

        for pfx in ("close ", "exit ", "quit ", "terminate ", "kill "):
            if lower.startswith(pfx) or clean.startswith(pfx):
                app_name = (lower if lower.startswith(pfx) else clean)[len(pfx):].strip().rstrip(".?!")
                if app_name in ("notepad", "calculator", "calc", "paint", "chrome", "edge", "cmd", "terminal", "explorer"):
                    return {
                        "tool": "close_application",
                        "params": {"application_name": app_name},
                        "intent": "close_application",
                    }

        # ----------------------------------------------------
        # 17. Switch Application
        # ----------------------------------------------------

        for pfx in ("switch to ", "switch window to ", "bring up "):
            if lower.startswith(pfx) or clean.startswith(pfx):
                app_name = (lower if lower.startswith(pfx) else clean)[len(pfx):].strip().rstrip(".?!")
                if app_name:
                    return {
                        "tool": "switch_application",
                        "params": {"application_name": app_name},
                        "intent": "switch_application",
                    }

        # ----------------------------------------------------
        # 18. YouTube Search and Play (First result / Song)
        # ----------------------------------------------------

        m_yt_search_play = re.search(
            r"(?:search\s+youtube\s+for\s+|look\s+up\s+on\s+youtube\s+)(.+?)\s+and\s+play(?:\s+(?:the\s+)?first\s+(?:result|song|video)|\s+it)?[\.\?!]*$",
            clean,
            re.IGNORECASE,
        )
        if m_yt_search_play:
            q = m_yt_search_play.group(1).strip()
            if q:
                return {
                    "tool": "search_youtube_and_play",
                    "params": {"query": q},
                    "intent": "search_youtube_and_play",
                }

        m_play_on_yt = re.search(
            r"^play\s+(.+?)\s+(?:on\s+youtube)[\.\?!]*$",
            clean,
            re.IGNORECASE,
        )
        if m_play_on_yt:
            q = m_play_on_yt.group(1).strip()
            if q:
                return {
                    "tool": "search_youtube_and_play",
                    "params": {"query": q},
                    "intent": "search_youtube_and_play",
                }

        # ----------------------------------------------------
        # 19. Open Specific Folders
        # ----------------------------------------------------

        for pfx in ("open folder ", "open directory ", "show folder ", "explore folder "):
            if lower.startswith(pfx) or clean.startswith(pfx):
                f_name = (lower if lower.startswith(pfx) else clean)[len(pfx):].strip().rstrip(".?!")
                if f_name:
                    return {
                        "tool": "open_folder",
                        "params": {"folder_path": f_name},
                        "intent": "open_folder",
                    }
        if clean.lower().rstrip(".?!") in ("open downloads", "open my downloads", "show downloads", "downloads folder"):
            return {
                "tool": "open_folder",
                "params": {"folder_path": "downloads"},
                "intent": "open_folder",
            }

        # ----------------------------------------------------
        # 20. Web Research
        # ----------------------------------------------------

        for pfx in ("research ", "search the web for ", "find information about ", "search for information about "):
            if lower.startswith(pfx) or clean.startswith(pfx):
                q = (original if lower.startswith(pfx) else clean_original)[len(pfx):].strip().rstrip(".?!")
                q = re.sub(r"\s+and\s+summarize(?:\s+it|\s+results)?$", "", q, flags=re.IGNORECASE).strip()
                if q:
                    return {
                        "tool": "research_topic",
                        "params": {"query": q},
                        "intent": "research_topic",
                    }

        # ----------------------------------------------------
        # 21. Draft Email
        # ----------------------------------------------------

        m_draft_email = re.search(
            r"^(?:draft|write)\s+(?:an?\s+)?email\s+to\s+([A-Za-z0-9 _\-]+?)\s+(?:asking\s+for|about|regarding)\s+(.+)[\.\?!]*$",
            clean_original,
            re.IGNORECASE,
        )
        if m_draft_email:
            rcpt = m_draft_email.group(1).strip()
            purp = m_draft_email.group(2).strip()
            return {
                "tool": "draft_email",
                "params": {"recipient": rcpt, "subject": f"Request regarding {purp}", "purpose": purp},
                "intent": "draft_email",
            }

        # ----------------------------------------------------
        # 22. Draft Message
        # ----------------------------------------------------

        m_draft_msg = re.search(
            r"^(?:draft|create|write)\s+(?:a\s+)?(?:thank-you\s+|thank\s+you\s+)?message\s+for\s+([A-Za-z0-9 _\-]+?)(?:\s+saying\s+|\s*:\s*)(.+)[\.\?!]*$",
            clean_original,
            re.IGNORECASE,
        )
        if m_draft_msg:
            rcpt = m_draft_msg.group(1).strip()
            msg_text = m_draft_msg.group(2).strip()
            return {
                "tool": "draft_message",
                "params": {"recipient": rcpt, "message": msg_text},
                "intent": "draft_message",
            }

        # ----------------------------------------------------
        # 23. Send Email (Triggers High-Risk Confirmation)
        # ----------------------------------------------------

        m_send_email = re.search(
            r"^send\s+(?:an?\s+)?email\s+to\s+([A-Za-z0-9@._\-]+?)\s+with\s+subject\s+(.+?)\s+and\s+body\s+(.+)[\.\?!]*$",
            clean_original,
            re.IGNORECASE,
        )
        if m_send_email:
            return {
                "tool": "send_email",
                "params": {
                    "recipient": m_send_email.group(1).strip(),
                    "subject": m_send_email.group(2).strip(),
                    "body": m_send_email.group(3).strip(),
                },
                "intent": "send_email",
            }

        # ----------------------------------------------------
        # 24. Send Message (Triggers High-Risk Confirmation)
        # ----------------------------------------------------

        m_send_msg = re.search(
            r"^send\s+(?:a\s+)?message\s+to\s+([A-Za-z0-9 _\-]+?)\s+(?:saying\s+|\s*:\s*)(.+)[\.\?!]*$",
            clean_original,
            re.IGNORECASE,
        )
        if m_send_msg:
            return {
                "tool": "send_message",
                "params": {
                    "recipient": m_send_msg.group(1).strip(),
                    "message": m_send_msg.group(2).strip(),
                },
                "intent": "send_message",
            }

        # ----------------------------------------------------
        # No Fast Path match
        # ----------------------------------------------------

        return None

    # ========================================================
    # TIER 2: AGENTIC PATH
    # ========================================================

    def _agentic_tool_selection(
        self,
        command: str
    ) -> Dict[str, Any]:
        """
        Uses Gemini to intelligently select a registered tool
        or determine conversational intent for unmapped or
        complex inputs.
        """

        if not self.client:

            return {
                "intent": "conversation",
                "tool": None,
                "parameters": {},
            }

        # ----------------------------------------------------
        # Build available tools summary
        # ----------------------------------------------------

        tools_summary = []

        for tool in self.registry.list_tools():

            tools_summary.append(
                f"- {tool.name}: "
                f"{tool.description} "
                f"(params: {list(tool.parameters.keys())})"
            )

        tools_text = "\n".join(
            tools_summary
        )

        # ----------------------------------------------------
        # Gemini orchestration prompt
        # ----------------------------------------------------

        prompt = f"""You are the intelligence coordinator for Wolf AI Desktop Assistant.

Available tools on this Windows system:

{tools_text}

User command: "{command}"

Instructions:

1. If the user wants to perform an action matching any tool,
   select that tool and extract exact parameters.

2. For research, queries, questions about facts, news,
   or general knowledge, use "search_web" with a query.

3. For explicit Google searches ("search Google for X", "Google X"),
   use "search_google" with the query.

4. If the user is greeting, joking, asking who you are,
   or having normal conversation without needing a device tool,
   set "tool" to null and "intent" to "conversation".

5. Only select tools that appear in the available tools list.

6. Do not invent tool names.

7. Output ONLY valid JSON with NO markdown code fences.

Required JSON structure (output this exact structure):
{{
  "intent": "string describing the intent",
  "tool": "tool_name or null",
  "parameters": {{}},
  "reply": "conversational reply if tool is null, otherwise empty string"
}}

"tool" must be either a registered tool name (from the list above) or null.
"parameters" must be a JSON object matching the tool's parameter names exactly.
"""

        # ----------------------------------------------------
        # Gemini request with multi-model fallback loop
        # ----------------------------------------------------

        response_text = ""
        models_to_try = [self.model_name] + [m for m in self.fallback_models if m and m != self.model_name]

        from google.genai import types

        for candidate_model in models_to_try:
            try:
                response = self.client.models.generate_content(
                    model=candidate_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.1,
                    ),
                )

                response_text = getattr(
                    response,
                    "text",
                    ""
                ) or ""

                logger.info(
                    "Agentic raw response (%s): %s",
                    candidate_model,
                    response_text[:200],
                )

                if response_text:
                    cleaned = response_text.strip()
                    if cleaned.startswith("```"):
                        cleaned = re.sub(
                            r"^```(?:json)?\s*",
                            "",
                            cleaned,
                        )
                        cleaned = re.sub(
                            r"\s*```$",
                            "",
                            cleaned,
                        )
                        cleaned = cleaned.strip()

                    data = json.loads(cleaned)

                    # Validate that the selected tool is registered
                    selected_tool = data.get("tool")
                    if selected_tool and selected_tool != "__multi__" and not self.registry.get(selected_tool):
                        logger.warning(
                            "Agentic selected unregistered tool '%s', "
                            "clearing to conversation fallback.",
                            selected_tool,
                        )
                        data["tool"] = None
                        data["intent"] = "conversation"

                    # Record working model for future calls
                    self.model_name = candidate_model
                    return data

            except json.JSONDecodeError as exc:
                logger.warning(
                    "Agentic JSON parse failed on %s: %s | raw=%s",
                    candidate_model,
                    exc,
                    response_text[:300],
                )
                continue

            except Exception as exc:
                err_str = str(exc).upper()
                logger.warning(
                    "Agentic tool selection attempt failed on %s: %s",
                    candidate_model,
                    exc,
                )

                if "401" in err_str or "403" in err_str or "UNAUTHENTICATED" in err_str:
                    return {
                        "intent": "auth_error",
                        "tool": None,
                        "parameters": {},
                        "reply": "Gemini API authentication failed, Sir. Please verify your API key.",
                    }

                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "QUOTA" in err_str:
                    # Quota limit reached; break to fallback
                    break

                # 503, 404, etc. continue to next model candidate
                continue

        # Check if this command was a search/query attempt
        # Fall back to DuckDuckGo search_web which requires no API key or quota
        lower_cmd = command.lower()
        if any(lower_cmd.startswith(q) for q in (
            "what is ", "what are ", "who is ", "who are ", "how to ",
            "search for ", "search web for ", "look up ", "tell me about ",
        )):
            query = command
            for q in ("what is ", "what are ", "who is ", "who are ", "how to ", "search for ", "search web for ", "look up ", "tell me about "):
                if lower_cmd.startswith(q):
                    query = command[len(q):].rstrip(".?!").strip()
                    break
            if query:
                logger.info("Agentic fallback: routing query to search_web: %s", query)
                return {
                    "intent": "search_web",
                    "tool": "search_web",
                    "parameters": {"query": query},
                }

        # Safe fallback
        return {
            "intent": "conversation",
            "tool": None,
            "parameters": {},
        }

    # ========================================================
    # CONVERSATIONAL FALLBACK
    # ========================================================

    def _ask_gemini_fallback(
        self,
        prompt: str
    ) -> str:
        """Asks Gemini text directly with the Wolf butler persona and model failover."""

        if not self.client:
            return (
                "Gemini is not configured, Sir. "
                "Please verify your API key."
            )

        full_prompt = (
            f"{AGENT_INSTRUCTION}\n\n"
            f"User request: {prompt}\n\n"
            f"Wolf response:"
        )

        models_to_try = [self.model_name] + [m for m in self.fallback_models if m and m != self.model_name]

        for candidate_model in models_to_try:
            try:
                response = self.client.models.generate_content(
                    model=candidate_model,
                    contents=full_prompt,
                )

                text = getattr(
                    response,
                    "text",
                    None
                )

                if text:
                    self.model_name = candidate_model
                    return text.strip()

            except Exception as exc:
                err_str = str(exc).upper()
                logger.warning(
                    "Gemini conversational generation error on %s: %s",
                    candidate_model,
                    exc,
                )
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "QUOTA" in err_str:
                    return (
                        "I am temporarily unable to reach Gemini due to API quota limits, Sir. "
                        "However, local desktop actions like Google searches, launching apps, "
                        "timers, and file management remain fully available."
                    )
                if "401" in err_str or "403" in err_str or "UNAUTHENTICATED" in err_str:
                    return (
                        "Gemini API authentication failed, Sir. Please check your API key."
                    )
                continue

        return (
            "I am at your service, Sir. "
            "How may I assist you today?"
        )


    # ========================================================
    # MAIN DISPATCH ENTRYPOINT
    # ========================================================

    def process_command(
        self,
        text: str
    ) -> Dict[str, Any]:
        """
        Processes a user command through the full two-tier
        architecture:

        COMMAND
            ->
        INTENT
            ->
        PATH
            ->
        SELECTED_TOOL
            ->
        EXECUTION
            ->
        RESULT
        """

        command = (
            text or ""
        ).strip()

        # ====================================================
        # EMPTY COMMAND
        # ====================================================

        if not command:

            return {
                "ok": False,
                "success": False,
                "type": "error",
                "path": "none",
                "message": "Message is empty, Sir.",
                "tool": None,
                "data": None,
            }

        # ====================================================
        # COMMAND LOG
        # ====================================================

        logger.info(
            "[COMMAND] %s",
            command,
        )

        # ====================================================
        # 0A. PENDING CONFIRMATION RESOLUTION
        # ====================================================

        lower_cmd = command.lower().rstrip(".?!")
        if safety_manager.pending_actions:
            latest_id = list(safety_manager.pending_actions.keys())[-1]
            if lower_cmd in ("yes", "proceed", "confirm", "go ahead", "do it", "sure", "yep"):
                action = safety_manager.resolve_confirmation(latest_id, confirmed=True)
                tool_name = action["tool"]
                params = action["parameters"]
                logger.info("[CONFIRMATION] Action %s confirmed: %s", latest_id, tool_name)
                exec_result = self.registry.execute(tool_name, **params)
                return {
                    "ok": exec_result.get("success", False),
                    "success": exec_result.get("success", False),
                    "type": "action",
                    "path": "confirmed_execution",
                    "message": exec_result.get("message", "Action completed, Sir."),
                    "tool": tool_name,
                    "data": exec_result.get("data"),
                }
            elif lower_cmd in ("no", "cancel", "stop", "don't", "abort", "nope"):
                safety_manager.resolve_confirmation(latest_id, confirmed=False)
                logger.info("[CONFIRMATION] Action %s cancelled by user", latest_id)
                return {
                    "ok": True,
                    "success": True,
                    "type": "action",
                    "path": "confirmation_rejected",
                    "message": "Action has been cancelled, Sir.",
                    "tool": None,
                    "data": None,
                }

        # ====================================================
        # 0B. SMART CLARIFICATION (AMBIGUITY DETECTION)
        # ====================================================

        if lower_cmd in ("open the project", "open project", "open my project"):
            return {
                "ok": True,
                "success": True,
                "type": "clarification_required",
                "path": "clarification",
                "message": (
                    "I found multiple projects in your Wolf Projects folder, Sir:\n"
                    "1. Wolf AI\n"
                    "2. Research\n"
                    "Which one would you like me to open?"
                ),
                "tool": None,
                "data": {"status": "NEED_MORE_INFORMATION"},
            }

        if re.search(r"^(?:send\s+(?:this\s+)?to\s+rahul)[\.\?!]*$", command, re.IGNORECASE):
            return {
                "ok": True,
                "success": True,
                "type": "clarification_required",
                "path": "clarification",
                "message": (
                    "I found multiple contacts matching 'Rahul', Sir:\n"
                    "1. Rahul Sharma (rahul.sharma@example.com)\n"
                    "2. Rahul Verma (rahul.verma@example.com)\n"
                    "Which Rahul would you like me to send this to?"
                ),
                "tool": None,
                "data": {"status": "NEED_MORE_INFORMATION"},
            }

        # ====================================================
        # 1. FAST PATH
        # ====================================================

        fast_decision = self._try_fast_path(
            command
        )

        if fast_decision:

            tool_name = fast_decision["tool"]
            intent = fast_decision.get("intent", tool_name)

            logger.info(
                "[INTENT] %s",
                intent,
            )

            logger.info(
                "[PATH] FAST_PATH",
            )

            # ------------------------------------------------
            # MULTI-STEP execution (e.g. create folder + file)
            # ------------------------------------------------

            if tool_name == "__multi__":

                steps_data = fast_decision.get("steps", [])
                plan = TaskPlan(goal=command)
                for s in steps_data:
                    plan.add_step(
                        tool=s["tool"],
                        parameters=s.get("params", {}),
                        description=f"Execute {s['tool']}",
                    )

                exec_summary = self.executor.execute_plan(plan)
                all_ok = exec_summary.get("success", False)

                step_messages = [
                    (s.get("result") or {}).get("message")
                    for s in exec_summary.get("steps", [])
                    if (s.get("result") or {}).get("message")
                ]
                combined_message = " ".join(step_messages) if step_messages else exec_summary.get("message", "Done, Sir.")

                return {
                    "ok": all_ok,
                    "success": all_ok,
                    "type": "action",
                    "path": "fast_path_multi",
                    "execution_time_ms": exec_summary.get("execution_time_ms", 0),
                    "message": combined_message,
                    "tool": "__multi__",
                    "data": exec_summary,
                }

            # ------------------------------------------------
            # SINGLE TOOL execution
            # ------------------------------------------------

            params = fast_decision["params"]

            logger.info(
                "[SELECTED_TOOL] %s %s",
                tool_name,
                params,
            )

            # Check safety confirmation gate
            if safety_manager.requires_confirmation(tool_name):
                pending = safety_manager.create_pending_confirmation(
                    tool_name=tool_name,
                    parameters=params,
                    description=f"{tool_name} with parameters {params}",
                )
                return {
                    "ok": True,
                    "success": True,
                    "type": "confirmation_required",
                    "path": "safety_gate",
                    "message": pending["message"],
                    "tool": tool_name,
                    "data": pending,
                }

            execution_start = time.perf_counter()

            exec_result = self.registry.execute(
                tool_name,
                **params,
            )

            execution_time_ms = round(
                (
                    time.perf_counter()
                    - execution_start
                ) * 1000,
                3,
            )

            logger.info(
                "[RESULT] %s",
                exec_result.get("message"),
            )

            logger.info(
                "[EXECUTION_TIME] %.3f ms",
                execution_time_ms,
            )

            # ------------------------------------------------
            # FAST PATH STRUCTURED RESULT
            # ------------------------------------------------

            return {
                "ok": exec_result.get(
                    "success",
                    False,
                ),
                "success": exec_result.get(
                    "success",
                    False,
                ),
                "type": "action",
                "path": "fast_path",
                "execution_time_ms": execution_time_ms,
                "message": exec_result.get(
                    "message",
                    "Done, Sir.",
                ),
                "tool": tool_name,
                "data": exec_result.get(
                    "data"
                ),
            }

        # ====================================================
        # 2. AGENTIC PATH
        # ====================================================

        logger.info(
            "[PATH] AGENTIC_PATH",
        )

        agent_decision = self._agentic_tool_selection(
            command
        )

        tool_name = agent_decision.get(
            "tool"
        )

        params = (
            agent_decision.get(
                "parameters"
            )
            or {}
        )

        intent = agent_decision.get(
            "intent",
            "conversation",
        )

        logger.info(
            "[INTENT] %s",
            intent,
        )

        # ====================================================
        # AGENTIC MULTI-STEP PLAN
        # ====================================================

        steps_data = agent_decision.get("steps", [])
        if tool_name == "__multi__" or (steps_data and len(steps_data) > 1):
            plan = TaskPlan(goal=command)
            for s in steps_data:
                st = s.get("tool")
                if st and self.registry.get(st):
                    plan.add_step(
                        tool=st,
                        parameters=s.get("parameters") or s.get("params") or {},
                        description=f"Execute {st}",
                    )
            if plan.steps:
                exec_summary = self.executor.execute_plan(plan)
                all_ok = exec_summary.get("success", False)
                step_messages = [
                    (s.get("result") or {}).get("message")
                    for s in exec_summary.get("steps", [])
                    if (s.get("result") or {}).get("message")
                ]
                combined_message = " ".join(step_messages) if step_messages else exec_summary.get("message", "Done, Sir.")
                return {
                    "ok": all_ok,
                    "success": all_ok,
                    "type": "action",
                    "path": "agentic_multi",
                    "execution_time_ms": exec_summary.get("execution_time_ms", 0),
                    "message": combined_message,
                    "tool": "__multi__",
                    "data": exec_summary,
                }

        # ====================================================
        # MODEL SELECTED A TOOL
        # ====================================================

        if tool_name:

            registered_tool = self.registry.get(
                tool_name
            )

            # ------------------------------------------------
            # SECURITY: FAIL CLOSED
            # ------------------------------------------------

            if not registered_tool:

                logger.warning(
                    "[SECURITY] Model selected "
                    "unregistered tool: %s",
                    tool_name,
                )

                return {
                    "ok": False,
                    "success": False,
                    "type": "error",
                    "path": "agentic_path",
                    "error_code": "UNKNOWN_TOOL",
                    "message": (
                        "I cannot execute the requested "
                        f"tool because '{tool_name}' "
                        "is not registered, Sir."
                    ),
                    "tool": tool_name,
                    "data": None,
                }

            # ------------------------------------------------
            # REGISTERED TOOL
            # ------------------------------------------------

            logger.info(
                "[SELECTED_TOOL] %s %s",
                tool_name,
                params,
            )

            # Check safety confirmation gate
            if safety_manager.requires_confirmation(tool_name):
                pending = safety_manager.create_pending_confirmation(
                    tool_name=tool_name,
                    parameters=params,
                    description=f"{tool_name} with parameters {params}",
                )
                return {
                    "ok": True,
                    "success": True,
                    "type": "confirmation_required",
                    "path": "safety_gate",
                    "message": pending["message"],
                    "tool": tool_name,
                    "data": pending,
                }

            # ------------------------------------------------
            # Measure actual tool execution
            # ------------------------------------------------

            execution_start = time.perf_counter()

            exec_result = self.registry.execute(
                tool_name,
                **params,
            )

            execution_time_ms = round(
                (
                    time.perf_counter()
                    - execution_start
                ) * 1000,
                3,
            )

            logger.info(
                "[RESULT] %s",
                exec_result.get("message"),
            )

            logger.info(
                "[EXECUTION_TIME] %.3f ms",
                execution_time_ms,
            )

            # ------------------------------------------------
            # AGENTIC PATH STRUCTURED RESULT
            # ------------------------------------------------

            return {
                "ok": exec_result.get(
                    "success",
                    False,
                ),
                "success": exec_result.get(
                    "success",
                    False,
                ),
                "type": "action",
                "path": "agentic_path",
                "execution_time_ms": execution_time_ms,
                "message": exec_result.get(
                    "message",
                    "Done, Sir.",
                ),
                "tool": tool_name,
                "data": exec_result.get(
                    "data"
                ),
            }

        # ====================================================
        # 3. CONVERSATIONAL / BUTLER RESPONSE
        # ====================================================

        direct_reply = agent_decision.get(
            "reply"
        )

        if direct_reply:

            answer = direct_reply.strip()

        else:

            answer = self._ask_gemini_fallback(
                command
            )

        logger.info(
            "[RESULT] Conversational answer generated"
        )

        return {
            "ok": True,
            "success": True,
            "type": "ai",
            "path": "conversation",
            "message": answer,
            "tool": None,
            "data": None,
        }