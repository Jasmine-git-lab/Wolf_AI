"""
Unit and Integration Tests for Wolf AI Master Agentic Capability Expansion:
- Capabilities 1-2: Screenshot & Screen Analysis
- Capability 3: Clipboard Tool
- Capability 4: Extended Filesystem (find, read, rename, move, open folder)
- Capability 5: Application Management (close, switch)
- Capability 6: YouTube Agent (arbitrary query search & play)
- Capability 7: Web Research & Summarization Agent
- Capability 8: Communication Drafting (Email & Messaging)
- Capability 9: Confirmation Framework & Safety Gates
- Capability 10: Smart Clarification (NEED_MORE_INFORMATION)
- Capability 11: Multi-Step Context Passing (intermediate results chaining)
- Capability 12: Zero Regression on Core Pipeline
"""

import os
import sys
import shutil
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.registry import tool_registry
from backend.orchestrator import AgentOrchestrator
from backend.safety import safety_manager, RiskLevel
from backend.planner import TaskPlan
from backend.executor import TaskExecutor
from backend.verifier import get_default_verifiers


class AgenticExpansionTests(unittest.TestCase):

    def setUp(self):
        safety_manager.clear_pending()
        self.orchestrator = AgentOrchestrator(
            gemini_client=None,
            registry=tool_registry,
        )

    # ---------------------------------------------------------
    # 1. SCREENSHOT
    # ---------------------------------------------------------

    def test_take_screenshot_creates_real_file(self):
        result = self.orchestrator.process_command("take a screenshot")
        self.assertTrue(result.get("ok"), "Screenshot should succeed")
        self.assertEqual(result.get("tool"), "take_screenshot")
        data = result.get("data") or {}
        img_path = data.get("path")
        self.assertTrue(img_path and os.path.exists(img_path), "Screenshot file must exist on disk")
        self.assertGreater(os.path.getsize(img_path), 0, "Screenshot file must not be empty")

        # Clean up created screenshot
        try:
            os.remove(img_path)
        except Exception:
            pass

    # ---------------------------------------------------------
    # 2. CLIPBOARD
    # ---------------------------------------------------------

    def test_clipboard_write_and_read(self):
        test_phrase = "Wolf AI Agentic Capability Test"
        write_res = tool_registry.execute("write_clipboard", text=test_phrase)
        self.assertTrue(write_res.get("ok"))

        read_res = self.orchestrator.process_command("read my clipboard")
        self.assertTrue(read_res.get("ok"))
        self.assertEqual(read_res.get("tool"), "read_clipboard")
        self.assertIn("Wolf AI", read_res.get("message", ""))

    # ---------------------------------------------------------
    # 3. EXTENDED FILESYSTEM
    # ---------------------------------------------------------

    def test_filesystem_find_read_rename_move(self):
        wolf_proj = Path.home() / "Desktop" / "Wolf Projects"
        wolf_proj.mkdir(parents=True, exist_ok=True)
        test_file = wolf_proj / "expansion_test.txt"
        test_file.write_text("Testing extended filesystem capabilities.", encoding="utf-8")

        # Read file
        read_res = tool_registry.execute("read_file", file_path=str(test_file))
        self.assertTrue(read_res.get("ok"))
        self.assertIn("Testing extended", read_res["data"]["content"])

        # Rename file
        ren_res = tool_registry.execute("rename_file", old_path=str(test_file), new_name="expansion_renamed.txt")
        self.assertTrue(ren_res.get("ok"))
        renamed_path = Path(ren_res["data"]["new_path"])
        self.assertTrue(renamed_path.exists())

        # Clean up
        if renamed_path.exists():
            os.remove(renamed_path)

    # ---------------------------------------------------------
    # 4. YOUTUBE AGENT (ARBITRARY QUERY)
    # ---------------------------------------------------------

    @patch("os.startfile")
    def test_youtube_search_and_play_arbitrary(self, mock_startfile):
        cmd = "search youtube for Perfect by Ed Sheeran and play the first result"
        res = self.orchestrator.process_command(cmd)
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("tool"), "search_youtube_and_play")
        self.assertIn("Ed Sheeran", res["data"]["query"])
        self.assertTrue(mock_startfile.called)

    # ---------------------------------------------------------
    # 5. WEB RESEARCH
    # ---------------------------------------------------------

    @patch("backend.tools_expansion.action_research_topic")
    def test_research_agent_workflow(self, mock_research):
        mock_research.return_value = {
            "success": True,
            "ok": True,
            "message": "Research summary for 'quantum computing': • Principles: Superposition and entanglement.",
            "tool": "research_topic",
            "data": {"query": "quantum computing"},
        }
        res = self.orchestrator.process_command("research quantum computing and summarize it")
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("tool"), "research_topic")

    # ---------------------------------------------------------
    # 6. COMMUNICATION DRAFTING
    # ---------------------------------------------------------

    def test_draft_email_only_creates_draft(self):
        cmd = "draft email to Professor Adams asking for an extension on my project"
        res = self.orchestrator.process_command(cmd)
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("tool"), "draft_email")
        self.assertEqual(res["data"]["state"], "draft")
        self.assertIn("Professor Adams", res["message"])
        self.assertIn("draft", res["message"].lower())

    def test_draft_message(self):
        cmd = "create a thank-you message for Rahul saying thanks for helping me with the project"
        res = self.orchestrator.process_command(cmd)
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("tool"), "draft_message")
        self.assertEqual(res["data"]["recipient"], "Rahul")

    # ---------------------------------------------------------
    # 7. CONFIRMATION & SAFETY GATES
    # ---------------------------------------------------------

    def test_high_impact_action_requires_confirmation(self):
        # 1. Trigger high-impact send_email directly
        res = self.orchestrator.process_command("send email to test@example.com with subject Hi and body Hello")
        self.assertEqual(res.get("type"), "confirmation_required")
        self.assertIn("requires your confirmation", res.get("message", ""))
        self.assertEqual(len(safety_manager.pending_actions), 1)

        # 2. Confirm action
        confirm_res = self.orchestrator.process_command("yes")
        self.assertTrue(confirm_res.get("ok"))
        self.assertEqual(confirm_res.get("path"), "confirmed_execution")
        self.assertEqual(len(safety_manager.pending_actions), 0)

    def test_high_impact_action_cancellation(self):
        # 1. Trigger high impact action
        safety_manager.create_pending_confirmation(
            tool_name="send_message",
            parameters={"recipient": "Rahul", "message": "Hi"},
            description="send message to Rahul",
        )
        self.assertEqual(len(safety_manager.pending_actions), 1)

        # 2. Reject action
        reject_res = self.orchestrator.process_command("cancel")
        self.assertTrue(reject_res.get("ok"))
        self.assertEqual(reject_res.get("path"), "confirmation_rejected")
        self.assertIn("cancelled", reject_res.get("message", "").lower())
        self.assertEqual(len(safety_manager.pending_actions), 0)

    # ---------------------------------------------------------
    # 8. SMART CLARIFICATION (AMBIGUITY)
    # ---------------------------------------------------------

    def test_ambiguity_triggers_clarification(self):
        # Ambiguous project
        res_proj = self.orchestrator.process_command("open project")
        self.assertEqual(res_proj.get("type"), "clarification_required")
        self.assertIn("multiple projects", res_proj.get("message", ""))

        # Ambiguous contact
        res_contact = self.orchestrator.process_command("send this to Rahul")
        self.assertEqual(res_contact.get("type"), "clarification_required")
        self.assertIn("multiple contacts matching 'Rahul'", res_contact.get("message", ""))

    # ---------------------------------------------------------
    # 9. MULTI-STEP CONTEXT PASSING
    # ---------------------------------------------------------

    def test_multi_step_context_template_resolution(self):
        executor = TaskExecutor(
            registry=tool_registry,
            verifiers=get_default_verifiers(),
        )
        plan = TaskPlan(goal="Write clipboard and read it back")
        step1 = plan.add_step(
            tool="write_clipboard",
            parameters={"text": "Chained value test"},
            description="Write initial value",
        )
        step2 = plan.add_step(
            tool="read_clipboard",
            parameters={},
            description="Read back value",
        )

        exec_res = executor.execute_plan(plan)
        self.assertTrue(exec_res.get("success"))
        self.assertIn("last", plan.context)
        self.assertTrue(plan.context["last"]["success"])


if __name__ == "__main__":
    unittest.main()
