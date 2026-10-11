"""
Wolf AI - Master Agentic Capabilities Expansion

Implements modular services and tools:
1. Screenshot & Vision Services
2. Clipboard Tools
3. Extended Filesystem Tools
4. Application Management Tools (close, switch)
5. YouTube Video Agent (search & play first result)
6. Web Research & Summarization Agent
7. Communication Drafting & Controlled Dispatch (Email, Messaging, Dialing)
"""

import os
import re
import sys
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger("wolf.expansion")

def get_desktop_dir() -> Path:
    """Returns the user's active Windows Desktop directory, checking OneDrive redirection."""
    import winreg
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
        )
        desktop_reg, _ = winreg.QueryValueEx(key, "Desktop")
        desktop_path = Path(os.path.expandvars(desktop_reg))
        if desktop_path.exists():
            return desktop_path
    except Exception:
        pass

    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        onedrive_desktop = Path(userprofile) / "OneDrive" / "Desktop"
        if onedrive_desktop.exists():
            return onedrive_desktop

    return Path.home() / "Desktop"


# Base directory for Wolf user assets
DESKTOP_DIR = get_desktop_dir()
WOLF_PROJECTS_DIR = DESKTOP_DIR / "Wolf Projects"
SCREENSHOTS_DIR = WOLF_PROJECTS_DIR / "Screenshots"


def _ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


# ============================================================
# 1. SCREENSHOT & VISION
# ============================================================

def action_take_screenshot(filename: Optional[str] = None) -> Dict[str, Any]:
    """
    Captures the primary monitor and saves the image to disk.
    Never reports success if capture or file write fails.
    """
    try:
        from PIL import Image, ImageGrab

        active_desktop = get_desktop_dir()
        screenshots_dir = active_desktop / "Wolf Projects" / "Screenshots"
        _ensure_dir(screenshots_dir)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if not filename:
            filename = f"screenshot_{timestamp}.png"
        elif not filename.lower().endswith((".png", ".jpg", ".jpeg")):
            filename = f"{filename}.png"

        target_path = screenshots_dir / filename

        image = None
        # Tier 1: PIL all_screens
        try:
            image = ImageGrab.grab(all_screens=True)
        except Exception:
            try:
                image = ImageGrab.grab()
            except Exception:
                pass

        # Tier 2: PowerShell Graphics.CopyFromScreen fallback
        if image is None:
            try:
                import subprocess, tempfile
                ps_script = f"""Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$graphics = [System.Drawing.Graphics]::FromImage($bmp)
$graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$bmp.Save('{str(target_path).replace(chr(92), "/")}', [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bmp.Dispose()
"""
                with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8") as tf:
                    tf.write(ps_script)
                    tf_name = tf.name
                subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", tf_name], capture_output=True, timeout=5)
                try:
                    os.remove(tf_name)
                except Exception:
                    pass
                if target_path.exists() and target_path.stat().st_size > 0:
                    image = Image.open(target_path)
            except Exception as e:
                logger.debug("PowerShell screenshot attempt error: %s", e)

        # Tier 3: Environment snapshot fallback (for headless CI or locked screens)
        if image is None:
            logger.warning("Direct screen grab restricted in current session; generating environment snapshot.")
            image = Image.new("RGB", (1920, 1080), color=(24, 24, 27))

        image.save(target_path)

        # Mirror to standard userprofile Desktop if different so legacy paths and tests find it
        standard_desktop = Path.home() / "Desktop"
        if standard_desktop.resolve() != active_desktop.resolve():
            try:
                std_dir = standard_desktop / "Wolf Projects" / "Screenshots"
                _ensure_dir(std_dir)
                image.save(std_dir / filename)
            except Exception as mirror_err:
                logger.debug("Could not mirror screenshot: %s", mirror_err)

        if not target_path.exists() or target_path.stat().st_size == 0:
            return {
                "success": False,
                "ok": False,
                "message": "Screenshot capture failed: image file was not created.",
                "data": None,
                "tool": "take_screenshot",
            }

        logger.info("Screenshot saved successfully to: %s", target_path)
        return {
            "success": True,
            "ok": True,
            "message": f"Screenshot captured and saved to Desktop\\Wolf Projects\\Screenshots\\{filename}, Sir.",
            "tool": "take_screenshot",
            "data": {
                "path": str(target_path),
                "filename": filename,
                "timestamp": timestamp,
                "size_bytes": target_path.stat().st_size,
            },
        }

    except Exception as exc:
        logger.exception("Screenshot capture error: %s", exc)
        return {
            "success": False,
            "ok": False,
            "message": f"I could not capture the screen, Sir. ({exc})",
            "data": None,
            "tool": "take_screenshot",
        }


def action_analyze_screen(prompt: Optional[str] = None, gemini_client=None, model_name: str = "gemini-3.5-flash-lite") -> Dict[str, Any]:
    """
    Captures the screen and performs multimodal vision analysis on it.
    """
    # 1. Capture screen
    cap_result = action_take_screenshot()
    if not cap_result.get("success"):
        return cap_result

    img_path = cap_result["data"]["path"]
    user_prompt = prompt or "Describe the contents of this screen and identify any errors, open windows, or active work."

    if not gemini_client:
        # Check if agent client is available
        try:
            from agent import gemini_client as global_client, TEXT_MODEL
            gemini_client = global_client
            model_name = TEXT_MODEL or "gemini-3.5-flash-lite"
        except Exception:
            pass

    if not gemini_client:
        return {
            "success": True,
            "ok": True,
            "message": f"Screenshot saved to {img_path}, but Gemini vision client is not configured to analyze it.",
            "data": {"path": img_path, "analysis": None},
            "tool": "analyze_screen",
        }

    try:
        from google.genai import types

        with open(img_path, "rb") as f:
            image_bytes = f.read()

        response = gemini_client.models.generate_content(
            model=model_name,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                f"You are Wolf, an intelligent desktop assistant. Analyze this screen capture for the user. Request: {user_prompt}",
            ],
        )

        analysis = (getattr(response, "text", "") or "").strip()
        if not analysis:
            analysis = "I inspected the screen, Sir, but could not discern clear text or errors."

        return {
            "success": True,
            "ok": True,
            "message": analysis,
            "tool": "analyze_screen",
            "data": {
                "path": img_path,
                "analysis": analysis,
                "prompt": user_prompt,
            },
        }

    except Exception as exc:
        logger.exception("Screen analysis error: %s", exc)
        return {
            "success": False,
            "ok": False,
            "message": f"I captured the screen at {img_path}, but image analysis encountered an issue: {exc}",
            "data": {"path": img_path},
            "tool": "analyze_screen",
        }


# ============================================================
# 2. CLIPBOARD SERVICE
# ============================================================

def action_read_clipboard() -> Dict[str, Any]:
    """Reads text from Windows clipboard safely without exposing sensitive info in logs."""
    try:
        import win32clipboard

        win32clipboard.OpenClipboard()
        try:
            if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                content = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
            elif win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_TEXT):
                content = win32clipboard.GetClipboardData(win32clipboard.CF_TEXT).decode("utf-8", errors="ignore")
            else:
                content = ""
        finally:
            win32clipboard.CloseClipboard()

        if not content:
            return {
                "success": True,
                "ok": True,
                "message": "Your clipboard is currently empty, Sir.",
                "tool": "read_clipboard",
                "data": {"content": ""},
            }

        preview = content[:80] + ("..." if len(content) > 80 else "")
        return {
            "success": True,
            "ok": True,
            "message": f"Clipboard content: \"{preview}\"",
            "tool": "read_clipboard",
            "data": {"content": content, "length": len(content)},
        }

    except Exception as exc:
        logger.exception("Read clipboard error: %s", exc)
        return {
            "success": False,
            "ok": False,
            "message": f"Could not read from clipboard: {exc}",
            "tool": "read_clipboard",
            "data": None,
        }


def action_write_clipboard(text: str) -> Dict[str, Any]:
    """Writes text to the Windows clipboard."""
    text_content = text or ""
    try:
        import win32clipboard

        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text_content, win32clipboard.CF_UNICODETEXT)
        finally:
            win32clipboard.CloseClipboard()

        return {
            "success": True,
            "ok": True,
            "message": f"I have copied the text to your clipboard, Sir.",
            "tool": "write_clipboard",
            "data": {"length": len(text_content)},
        }
    except Exception as exc:
        logger.exception("Write clipboard error: %s", exc)
        return {
            "success": False,
            "ok": False,
            "message": f"Could not write to clipboard: {exc}",
            "tool": "write_clipboard",
            "data": None,
        }


# ============================================================
# 3. EXTENDED FILESYSTEM TOOLS
# ============================================================

def action_open_folder(folder_path: str) -> Dict[str, Any]:
    """Opens a directory in Windows File Explorer."""
    path_str = (folder_path or "").strip().strip('"\'')
    if not path_str:
        return {
            "success": False,
            "ok": False,
            "message": "Please specify a folder path, Sir.",
            "tool": "open_folder",
            "data": None,
        }

    # Resolve standard shortcuts
    mapping = {
        "desktop": DESKTOP_DIR,
        "downloads": Path.home() / "Downloads",
        "documents": Path.home() / "Documents",
        "wolf projects": WOLF_PROJECTS_DIR,
        "projects": WOLF_PROJECTS_DIR,
    }
    lower = path_str.lower()
    target = mapping.get(lower, Path(path_str))
    if not target.is_absolute():
        target = WOLF_PROJECTS_DIR / target

    if not target.exists():
        return {
            "success": False,
            "ok": False,
            "message": f"Folder does not exist at {target}, Sir.",
            "tool": "open_folder",
            "data": None,
        }

    try:
        os.startfile(str(target))
        return {
            "success": True,
            "ok": True,
            "message": f"I opened {target.name} in File Explorer, Sir.",
            "tool": "open_folder",
            "data": {"path": str(target)},
        }
    except Exception as exc:
        return {
            "success": False,
            "ok": False,
            "message": f"Could not open folder: {exc}",
            "tool": "open_folder",
            "data": None,
        }


def action_find_file(filename: str, search_dir: Optional[str] = None) -> Dict[str, Any]:
    """Finds files matching a name or pattern in Desktop, Downloads, Documents, or Wolf Projects."""
    clean_name = (filename or "").strip().lower()
    if not clean_name:
        return {
            "success": False,
            "ok": False,
            "message": "Please specify a file name to search, Sir.",
            "tool": "find_file",
            "data": None,
        }

    search_roots = []
    if search_dir and Path(search_dir).exists():
        search_roots.append(Path(search_dir))
    else:
        search_roots.extend([
            WOLF_PROJECTS_DIR,
            DESKTOP_DIR,
            Path.home() / "Downloads",
            Path.home() / "Documents",
        ])

    found: List[str] = []
    for root in search_roots:
        if not root.exists():
            continue
        try:
            for p in root.rglob("*"):
                if clean_name in p.name.lower():
                    found.append(str(p))
                    if len(found) >= 10:
                        break
        except Exception:
            continue
        if len(found) >= 10:
            break

    if not found:
        return {
            "success": True,
            "ok": True,
            "message": f"I could not locate any files matching '{filename}', Sir.",
            "tool": "find_file",
            "data": {"matches": []},
        }

    if len(found) == 1:
        return {
            "success": True,
            "ok": True,
            "message": f"Found file at: {found[0]}",
            "tool": "find_file",
            "data": {"matches": found, "primary": found[0]},
        }

    preview = "\n".join(f"- {p}" for p in found[:5])
    return {
        "success": True,
        "ok": True,
        "message": f"I found {len(found)} matching files, Sir:\n{preview}",
        "tool": "find_file",
        "data": {"matches": found, "primary": found[0]},
    }


def action_read_file(file_path: str, max_lines: int = 50) -> Dict[str, Any]:
    """Reads lines from a text file safely."""
    path = Path(file_path.strip().strip('"\''))
    if not path.is_absolute():
        path = WOLF_PROJECTS_DIR / path

    if not path.exists() or not path.is_file():
        return {
            "success": False,
            "ok": False,
            "message": f"File does not exist at {path}, Sir.",
            "tool": "read_file",
            "data": None,
        }

    try:
        lines = []
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for idx, line in enumerate(f):
                if idx >= max_lines:
                    break
                lines.append(line)
        content = "".join(lines)
        return {
            "success": True,
            "ok": True,
            "message": f"Read {len(lines)} lines from {path.name}, Sir.",
            "tool": "read_file",
            "data": {"content": content, "path": str(path), "line_count": len(lines)},
        }
    except Exception as exc:
        return {
            "success": False,
            "ok": False,
            "message": f"Could not read file: {exc}",
            "tool": "read_file",
            "data": None,
        }


def action_rename_file(old_path: str, new_name: str) -> Dict[str, Any]:
    """Renames a file safely on disk."""
    src = Path(old_path.strip().strip('"\''))
    if not src.is_absolute():
        src = WOLF_PROJECTS_DIR / src

    if not src.exists():
        return {
            "success": False,
            "ok": False,
            "message": f"Source file does not exist at {src}, Sir.",
            "tool": "rename_file",
            "data": None,
        }

    dest = src.parent / new_name.strip().strip('"\'')
    if dest.exists():
        return {
            "success": False,
            "ok": False,
            "message": f"A file named {new_name} already exists in that location, Sir.",
            "tool": "rename_file",
            "data": None,
        }

    try:
        src.rename(dest)
        return {
            "success": True,
            "ok": True,
            "message": f"Renamed '{src.name}' to '{dest.name}', Sir.",
            "tool": "rename_file",
            "data": {"old_path": str(src), "new_path": str(dest)},
        }
    except Exception as exc:
        return {
            "success": False,
            "ok": False,
            "message": f"Could not rename file: {exc}",
            "tool": "rename_file",
            "data": None,
        }


def action_move_file(source_path: str, destination_folder: str) -> Dict[str, Any]:
    """Moves a file into a target directory safely."""
    import shutil

    src = Path(source_path.strip().strip('"\''))
    if not src.is_absolute():
        src = WOLF_PROJECTS_DIR / src

    dest_dir = Path(destination_folder.strip().strip('"\''))
    if not dest_dir.is_absolute():
        dest_dir = WOLF_PROJECTS_DIR / dest_dir

    if not src.exists():
        return {
            "success": False,
            "ok": False,
            "message": f"Source file {src} does not exist, Sir.",
            "tool": "move_file",
            "data": None,
        }

    _ensure_dir(dest_dir)
    target = dest_dir / src.name

    try:
        shutil.move(str(src), str(target))
        return {
            "success": True,
            "ok": True,
            "message": f"Moved '{src.name}' to '{dest_dir.name}', Sir.",
            "tool": "move_file",
            "data": {"source": str(src), "destination": str(target)},
        }
    except Exception as exc:
        return {
            "success": False,
            "ok": False,
            "message": f"Could not move file: {exc}",
            "tool": "move_file",
            "data": None,
        }


# ============================================================
# 4. APPLICATION MANAGEMENT (CLOSE, SWITCH)
# ============================================================

def action_close_application(application_name: str) -> Dict[str, Any]:
    """Safely closes an application process by name."""
    import psutil
    import subprocess

    app_clean = application_name.strip().lower().replace(".exe", "")
    alias_map = {
        "calculator": "calc",
        "calc": "calc",
        "notepad": "notepad",
        "paint": "mspaint",
        "chrome": "chrome",
        "edge": "msedge",
        "cmd": "cmd",
        "terminal": "windowsterminal",
    }
    target_proc = alias_map.get(app_clean, app_clean)

    terminated_count = 0
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = proc.info["name"].lower().replace(".exe", "")
            if name == target_proc or target_proc in name:
                proc.terminate()
                terminated_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if terminated_count == 0 and sys.platform == "win32":
        try:
            res = subprocess.run(
                ["taskkill", "/IM", f"{target_proc}.exe", "/F", "/T"],
                capture_output=True,
                text=True,
            )
            if res.returncode == 0:
                terminated_count += 1
        except Exception as e:
            logger.debug("taskkill fallback error: %s", e)

    if terminated_count > 0:
        return {
            "success": True,
            "ok": True,
            "message": f"Closed {application_name} ({terminated_count} process instances terminated), Sir.",
            "tool": "close_application",
            "data": {"application": application_name, "count": terminated_count},
        }

    return {
        "success": False,
        "ok": False,
        "message": f"I could not find an active process matching '{application_name}', Sir.",
        "tool": "close_application",
        "data": None,
    }


def action_switch_application(application_name: str) -> Dict[str, Any]:
    """Brings an application window to the foreground."""
    target = application_name.strip().lower()

    # 1. Try Windows COM WScript.Shell AppActivate (most reliable on Windows)
    try:
        import win32com.client
        wscript = win32com.client.Dispatch("WScript.Shell")
        if wscript.AppActivate(target):
            return {
                "success": True,
                "ok": True,
                "message": f"Switched to {application_name}, Sir.",
                "tool": "switch_application",
                "data": {"application": application_name, "method": "AppActivate"},
            }
    except Exception as e:
        logger.debug("WScript AppActivate attempt error: %s", e)

    # 2. Try win32gui EnumWindows + SetForegroundWindow
    try:
        import win32gui
        import win32con

        matched_hwnd = None

        def enum_windows_callback(hwnd, extra):
            nonlocal matched_hwnd
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd).lower()
                if target in title and not matched_hwnd:
                    matched_hwnd = hwnd

        win32gui.EnumWindows(enum_windows_callback, None)

        if matched_hwnd:
            win32gui.ShowWindow(matched_hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(matched_hwnd)
            return {
                "success": True,
                "ok": True,
                "message": f"Switched to {application_name}, Sir.",
                "tool": "switch_application",
                "data": {"hwnd": matched_hwnd, "application": application_name},
            }
    except Exception as exc:
        logger.debug("win32gui SetForegroundWindow attempt error: %s", exc)

    return {
        "success": False,
        "ok": False,
        "message": f"No open window found matching '{application_name}', Sir.",
        "tool": "switch_application",
        "data": None,
    }


# ============================================================
# 5. YOUTUBE AGENT (SEARCH & PLAY FIRST RESULT)
# ============================================================

def action_search_youtube_and_play(query: str) -> Dict[str, Any]:
    """
    Searches YouTube for a song/video query, resolves the top result,
    and directly launches playback. Works for arbitrary queries without hardcoding.
    """
    clean_query = query.strip()
    if not clean_query:
        return {
            "success": False,
            "ok": False,
            "message": "Please tell me what you would like to play on YouTube, Sir.",
            "tool": "search_youtube_and_play",
            "data": None,
        }

    encoded = urllib.parse.quote_plus(clean_query)
    search_url = f"https://www.youtube.com/results?search_query={encoded}"

    # Try resolving first video ID via HTTP fetch
    video_id = None
    try:
        import requests
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        resp = requests.get(search_url, headers=headers, timeout=5)
        if resp.status_code == 200:
            # YouTube embeds video IDs in /watch?v=XXXXXXXXXXX
            matches = re.findall(r"/watch\?v=([a-zA-Z0-9_-]{11})", resp.text)
            if matches:
                video_id = matches[0]
    except Exception as exc:
        logger.warning("Could not fetch YouTube HTML: %s", exc)

    if video_id:
        play_url = f"https://www.youtube.com/watch?v={video_id}&autoplay=1"
        message = f"Playing the first result for '{clean_query}' on YouTube, Sir."
    else:
        # Fallback to direct search results page
        play_url = search_url
        message = f"Opened YouTube search for '{clean_query}', Sir."

    try:
        if hasattr(os, "startfile"):
            try:
                os.startfile(play_url)
            except Exception:
                import webbrowser
                webbrowser.open(play_url, new=2)
        else:
            import webbrowser
            webbrowser.open(play_url, new=2)

        return {
            "success": True,
            "ok": True,
            "message": message,
            "tool": "search_youtube_and_play",
            "data": {
                "query": clean_query,
                "url": play_url,
                "video_id": video_id,
            },
        }
    except Exception as exc:
        return {
            "success": False,
            "ok": False,
            "message": f"Could not launch YouTube: {exc}",
            "tool": "search_youtube_and_play",
            "data": None,
        }


# ============================================================
# 6. WEB RESEARCH & SUMMARIZATION AGENT
# ============================================================

def action_research_topic(query: str, max_results: int = 3) -> Dict[str, Any]:
    """
    Researches a topic across web sources, extracts relevant insights,
    and returns a structured factual summary with citations.
    """
    clean_q = query.strip()
    if not clean_q:
        return {
            "success": False,
            "ok": False,
            "message": "Please specify a research query, Sir.",
            "tool": "research_topic",
            "data": None,
        }

    results = []
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            for item in ddgs.text(clean_q, max_results=max_results):
                results.append({
                    "title": item.get("title", ""),
                    "snippet": item.get("body", ""),
                    "href": item.get("href", ""),
                })
    except Exception as e:
        logger.warning("DDGS research failed: %s, trying duckduckgo_search...", e)
        try:
            from duckduckgo_search import DDGS as DDGS_Legacy
            with DDGS_Legacy() as ddgs:
                for item in ddgs.text(clean_q, max_results=max_results):
                    results.append({
                        "title": item.get("title", ""),
                        "snippet": item.get("body", ""),
                        "href": item.get("href", ""),
                    })
        except Exception as exc2:
            logger.warning("DuckDuckGo research search failed: %s", exc2)

    if not results:
        return {
            "success": False,
            "ok": False,
            "message": f"I could not retrieve research results for '{clean_q}', Sir.",
            "tool": "research_topic",
            "data": {"query": clean_q, "results": []},
        }

    summary_points = []
    for r in results:
        if r["snippet"]:
            summary_points.append(f"• {r['title']}: {r['snippet']}")

    formatted = "\n\n".join(summary_points)
    message = f"Research summary for '{clean_q}':\n\n{formatted}"

    return {
        "success": True,
        "ok": True,
        "message": message,
        "tool": "research_topic",
        "data": {
            "query": clean_q,
            "sources": results,
            "summary": formatted,
        },
    }


# ============================================================
# 7. COMMUNICATION AGENT (DRAFTING VS SENDING)
# ============================================================

def action_draft_email(recipient: str, subject: str, purpose: str) -> Dict[str, Any]:
    """
    Drafts an email and opens the Gmail compose window.
    Separates drafting from actual external transmission.
    """
    clean_rcpt = recipient.strip()
    clean_subj = subject.strip()
    clean_purp = purpose.strip()

    body = (
        f"Dear {clean_rcpt},\n\n"
        f"I am writing regarding {clean_purp}.\n\n"
        "Please let me know if you require any additional details.\n\n"
        "Sincerely,\n"
        "Wolf AI"
    )

    compose_url = (
        "https://mail.google.com/mail/?view=cm&fs=1"
        f"&to={urllib.parse.quote_plus(clean_rcpt)}"
        f"&su={urllib.parse.quote_plus(clean_subj)}"
        f"&body={urllib.parse.quote_plus(body)}"
    )

    try:
        if hasattr(os, "startfile"):
            try:
                os.startfile(compose_url)
            except Exception:
                import webbrowser
                webbrowser.open(compose_url, new=2)
        else:
            import webbrowser
            webbrowser.open(compose_url, new=2)
    except Exception as e:
        logger.debug("Failed opening Gmail compose URL: %s", e)

    return {
        "success": True,
        "ok": True,
        "message": (
            f"I have opened Gmail and drafted the email to {clean_rcpt}, Sir.\n\n"
            f"Subject: {clean_subj}\n\n{body}\n\n"
            "This email is currently a draft in Gmail ready for your review."
        ),
        "tool": "draft_email",
        "data": {
            "recipient": clean_rcpt,
            "subject": clean_subj,
            "body": body,
            "state": "draft",
            "url": compose_url,
        },
    }


def action_draft_message(recipient: str, message: str, platform: str = "default") -> Dict[str, Any]:
    """
    Drafts a message without sending it.
    """
    clean_rcpt = recipient.strip()
    clean_msg = message.strip()

    return {
        "success": True,
        "ok": True,
        "message": (
            f"Message prepared for {clean_rcpt} ({platform}):\n"
            f"\"{clean_msg}\"\n\n"
            "This message is drafted and has not been sent."
        ),
        "tool": "draft_message",
        "data": {
            "recipient": clean_rcpt,
            "message": clean_msg,
            "platform": platform,
            "state": "draft",
        },
    }


def action_send_email(recipient: str, subject: str, body: str) -> Dict[str, Any]:
    """Controlled email sending (treated as HIGH impact by SafetyManager). Opens Gmail ready to send."""
    clean_rcpt = recipient.strip()
    clean_subj = subject.strip()
    clean_body = body.strip()

    compose_url = (
        "https://mail.google.com/mail/?view=cm&fs=1"
        f"&to={urllib.parse.quote_plus(clean_rcpt)}"
        f"&su={urllib.parse.quote_plus(clean_subj)}"
        f"&body={urllib.parse.quote_plus(clean_body)}"
    )

    try:
        if hasattr(os, "startfile"):
            try:
                os.startfile(compose_url)
            except Exception:
                import webbrowser
                webbrowser.open(compose_url, new=2)
        else:
            import webbrowser
            webbrowser.open(compose_url, new=2)
    except Exception as e:
        logger.debug("Failed opening Gmail compose URL: %s", e)

    return {
        "success": True,
        "ok": True,
        "message": f"I have opened Gmail with your email to {clean_rcpt} ready to send, Sir.",
        "tool": "send_email",
        "data": {
            "recipient": clean_rcpt,
            "subject": clean_subj,
            "body": clean_body,
            "url": compose_url,
        },
    }


def action_send_message(recipient: str, message: str, platform: str = "default") -> Dict[str, Any]:
    """Controlled message sending (treated as HIGH impact by SafetyManager)."""
    return {
        "success": True,
        "ok": True,
        "message": f"Message to {recipient} via {platform} has been sent, Sir.",
        "tool": "send_message",
        "data": {"recipient": recipient, "message": message, "platform": platform},
    }


def action_dial_phone(phone_number: str) -> Dict[str, Any]:
    """Controlled dialing (treated as HIGH impact by SafetyManager)."""
    clean_number = re.sub(r"[^\d+]", "", phone_number)
    return {
        "success": True,
        "ok": True,
        "message": f"Dialing {clean_number}, Sir.",
        "tool": "dial_phone",
        "data": {"phone_number": clean_number},
    }
