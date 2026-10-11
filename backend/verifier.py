"""
Wolf AI - Phase 2 Execution Verifiers

Verifies actual filesystem, process, and system changes after tool execution.
Never reports success if an operation failed on disk or system.
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any

from backend.planner import TaskStep
from backend.tools_expansion import get_desktop_dir

logger = logging.getLogger("wolf.verifier")


def verify_create_folder(step: TaskStep, result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Verifies that the requested folder was actually created on disk.
    """
    if result.get("success") is not True:
        return {"success": False, "message": "Tool execution reported failure."}

    data = result.get("data") or {}
    folder_path = data.get("path") or step.parameters.get("path")

    if not folder_path:
        folder_name = step.parameters.get("folder_name") or step.parameters.get("name")
        if folder_name:
            candidates = [
                get_desktop_dir() / "Wolf Projects" / folder_name,
                get_desktop_dir() / folder_name,
                Path.home() / "Desktop" / "Wolf Projects" / folder_name,
                Path.home() / "Desktop" / folder_name,
            ]
            for c in candidates:
                if c.exists() and c.is_dir():
                    folder_path = str(c)
                    break

    if not folder_path or not os.path.exists(folder_path):
        return {
            "success": False,
            "message": f"Verification failed: folder does not exist at {folder_path}."
        }

    if not os.path.isdir(folder_path):
        return {
            "success": False,
            "message": f"Verification failed: path exists but is not a directory at {folder_path}."
        }

    logger.info("Folder creation verified at: %s", folder_path)
    return {
        "success": True,
        "message": f"Verified: folder exists at {folder_path}.",
        "path": folder_path
    }


def verify_create_file(step: TaskStep, result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Verifies that the requested file was actually created on disk.
    """
    if result.get("success") is not True:
        return {"success": False, "message": "Tool execution reported failure."}

    data = result.get("data") or {}
    file_path = data.get("path") or step.parameters.get("path")

    if not file_path:
        file_name = step.parameters.get("file_name") or step.parameters.get("name")
        folder_name = step.parameters.get("folder_name")
        if file_name:
            candidates = []
            if folder_name:
                candidates.extend([
                    get_desktop_dir() / "Wolf Projects" / folder_name / file_name,
                    get_desktop_dir() / folder_name / file_name,
                    Path.home() / "Desktop" / "Wolf Projects" / folder_name / file_name,
                    Path.home() / "Desktop" / folder_name / file_name,
                ])
            candidates.extend([
                get_desktop_dir() / "Wolf Projects" / file_name,
                get_desktop_dir() / file_name,
                Path.home() / "Desktop" / "Wolf Projects" / file_name,
                Path.home() / "Desktop" / file_name,
            ])
            for c in candidates:
                if c.exists() and c.is_file():
                    file_path = str(c)
                    break

    if not file_path or not os.path.exists(file_path):
        return {
            "success": False,
            "message": f"Verification failed: file does not exist at {file_path}."
        }

    if not os.path.isfile(file_path):
        return {
            "success": False,
            "message": f"Verification failed: path exists but is not a regular file at {file_path}."
        }

    logger.info("File creation verified at: %s", file_path)
    return {
        "success": True,
        "message": f"Verified: file exists at {file_path}.",
        "path": file_path
    }


def verify_take_screenshot(step: TaskStep, result: Dict[str, Any]) -> Dict[str, Any]:
    """Verifies that the screenshot file was actually created and is non-empty."""
    if result.get("success") is not True:
        return {"success": False, "message": "Screenshot capture reported failure."}

    data = result.get("data") or {}
    path = data.get("path")
    if not path or not os.path.exists(path):
        # Check active and standard screenshot dirs
        filename = data.get("filename")
        if filename:
            for s_dir in (get_desktop_dir() / "Wolf Projects" / "Screenshots", Path.home() / "Desktop" / "Wolf Projects" / "Screenshots"):
                candidate = s_dir / filename
                if candidate.exists():
                    path = str(candidate)
                    break

    if not path or not os.path.exists(path):
        return {"success": False, "message": f"Screenshot verification failed: file does not exist at {path}."}

    if os.path.getsize(path) == 0:
        return {"success": False, "message": "Screenshot verification failed: file size is 0 bytes."}

    logger.info("Screenshot verified at: %s", path)
    return {"success": True, "message": f"Verified: screenshot saved at {path}.", "path": path}


def verify_rename_file(step: TaskStep, result: Dict[str, Any]) -> Dict[str, Any]:
    """Verifies that the renamed file exists at the new path."""
    if result.get("success") is not True:
        return {"success": False, "message": "File rename reported failure."}

    data = result.get("data") or {}
    new_path = data.get("new_path")
    if not new_path or not os.path.exists(new_path):
        return {"success": False, "message": f"Rename verification failed: file does not exist at {new_path}."}

    return {"success": True, "message": f"Verified: file exists at {new_path}.", "path": new_path}


def verify_move_file(step: TaskStep, result: Dict[str, Any]) -> Dict[str, Any]:
    """Verifies that the moved file exists at the destination path."""
    if result.get("success") is not True:
        return {"success": False, "message": "File move reported failure."}

    data = result.get("data") or {}
    dest = data.get("destination")
    if not dest or not os.path.exists(dest):
        return {"success": False, "message": f"Move verification failed: file does not exist at {dest}."}

    return {"success": True, "message": f"Verified: file exists at {dest}.", "path": dest}


def get_default_verifiers() -> Dict[str, Any]:
    return {
        "create_folder": verify_create_folder,
        "create_project_folder": verify_create_folder,
        "create_file": verify_create_file,
        "take_screenshot": verify_take_screenshot,
        "rename_file": verify_rename_file,
        "move_file": verify_move_file,
    }
