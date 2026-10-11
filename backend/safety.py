"""
Wolf AI - Safety & Confirmation Framework

Classifies tool actions by risk level:
- LOW: read-only, local captures, launches (executes immediately)
- MEDIUM: non-destructive file writes, clipboard modifications
- HIGH: external messaging, emails, phone calls, file deletions (requires explicit confirmation)
"""

import logging
from enum import Enum
from typing import Dict, Any, Optional
from uuid import uuid4

logger = logging.getLogger("wolf.safety")


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ConfirmationState(str, Enum):
    NONE = "none"
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


# Tool risk definitions
TOOL_RISK_MAP = {
    # Low Risk (immediate execution)
    "take_screenshot": RiskLevel.LOW,
    "analyze_screen": RiskLevel.LOW,
    "read_clipboard": RiskLevel.LOW,
    "open_application": RiskLevel.LOW,
    "open_file_explorer": RiskLevel.LOW,
    "open_folder": RiskLevel.LOW,
    "find_file": RiskLevel.LOW,
    "read_file": RiskLevel.LOW,
    "open_google": RiskLevel.LOW,
    "open_youtube": RiskLevel.LOW,
    "open_gmail": RiskLevel.LOW,
    "open_website": RiskLevel.LOW,
    "search_google": RiskLevel.LOW,
    "search_youtube": RiskLevel.LOW,
    "play_youtube": RiskLevel.LOW,
    "search_youtube_and_play": RiskLevel.LOW,
    "search_web": RiskLevel.LOW,
    "research_topic": RiskLevel.LOW,
    "get_weather": RiskLevel.LOW,
    "set_timer": RiskLevel.LOW,
    "motivate_user": RiskLevel.LOW,
    "draft_email": RiskLevel.LOW,
    "draft_message": RiskLevel.LOW,

    # Medium Risk (controlled execution)
    "create_folder": RiskLevel.MEDIUM,
    "create_project_folder": RiskLevel.MEDIUM,
    "create_file": RiskLevel.MEDIUM,
    "write_clipboard": RiskLevel.MEDIUM,
    "rename_file": RiskLevel.MEDIUM,
    "move_file": RiskLevel.MEDIUM,
    "switch_application": RiskLevel.MEDIUM,
    "close_application": RiskLevel.MEDIUM,

    # High Risk (Requires Confirmation)
    "send_email": RiskLevel.HIGH,
    "send_message": RiskLevel.HIGH,
    "dial_phone": RiskLevel.HIGH,
    "delete_file": RiskLevel.HIGH,
}


class SafetyManager:
    """
    Manages action safety, confirmation gates, and pending high-impact actions.
    """

    def __init__(self):
        self.pending_actions: Dict[str, Dict[str, Any]] = {}

    def get_risk_level(self, tool_name: str) -> RiskLevel:
        return TOOL_RISK_MAP.get(tool_name, RiskLevel.MEDIUM)

    def requires_confirmation(self, tool_name: str) -> bool:
        return self.get_risk_level(tool_name) == RiskLevel.HIGH

    def create_pending_confirmation(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        description: str,
    ) -> Dict[str, Any]:
        """Registers an action that is awaiting user confirmation."""
        action_id = uuid4().hex[:8]
        self.pending_actions[action_id] = {
            "id": action_id,
            "tool": tool_name,
            "parameters": parameters,
            "description": description,
            "state": ConfirmationState.PENDING,
        }
        logger.info(
            "Created pending confirmation %s for high-impact tool '%s'",
            action_id,
            tool_name,
        )
        if tool_name == "send_email":
            rcpt = parameters.get("recipient", "the recipient")
            subj = parameters.get("subject", "")
            msg = (
                f"This is a high-risk action which requires your confirmation, Sir: "
                f"Send email to {rcpt} with subject '{subj}'. "
                f"Are you sure you want to proceed? Say 'yes' to confirm or 'cancel' to abort."
            )
        elif tool_name == "send_message":
            rcpt = parameters.get("recipient", "the recipient")
            msg = (
                f"This is a high-risk action which requires your confirmation, Sir: "
                f"Send message to {rcpt}. "
                f"Are you sure you want to proceed? Say 'yes' to confirm or 'cancel' to abort."
            )
        elif tool_name == "dial_phone":
            num = parameters.get("phone_number", "the number")
            msg = (
                f"This is a high-risk action which requires your confirmation, Sir: "
                f"Dial phone number {num}. "
                f"Are you sure you want to proceed? Say 'yes' to confirm or 'cancel' to abort."
            )
        else:
            msg = (
                f"Action '{description}' requires your confirmation, Sir. "
                "Would you like me to proceed? Say 'yes' to confirm or 'cancel' to abort."
            )

        return {
            "status": "CONFIRMATION_REQUIRED",
            "action_id": action_id,
            "tool": tool_name,
            "parameters": parameters,
            "message": msg,
        }

    def get_pending_action(self, action_id: str) -> Optional[Dict[str, Any]]:
        return self.pending_actions.get(action_id)

    def resolve_confirmation(
        self,
        action_id: str,
        confirmed: bool,
    ) -> Optional[Dict[str, Any]]:
        action = self.pending_actions.pop(action_id, None)
        if not action:
            return None
        action["state"] = ConfirmationState.CONFIRMED if confirmed else ConfirmationState.REJECTED
        return action

    def clear_pending(self) -> None:
        self.pending_actions.clear()


safety_manager = SafetyManager()
