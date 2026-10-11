"""Focused tests for Wolf AI Phase 1 registry/orchestrator safeguards."""
import unittest

from backend.registry import ToolDefinition, ToolRegistry
from backend.orchestrator import AgentOrchestrator


class ToolRegistryPhase1Tests(unittest.TestCase):
    def test_missing_required_parameter_is_rejected(self):
        tool = ToolDefinition("search", "search", {"query": {"type": "string"}}, lambda query: (True, query))
        result = tool.execute()
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "INVALID_PARAMETERS")

    def test_invalid_types_are_rejected(self):
        tool = ToolDefinition("timer", "timer", {"minutes": {"type": "number"}}, lambda minutes: (True, str(minutes)))
        self.assertFalse(tool.execute(minutes=True)["success"])
        self.assertFalse(tool.execute(minutes=float("nan"))["success"])
        self.assertTrue(tool.execute(minutes=1.5)["success"])

    def test_unexpected_parameter_is_rejected(self):
        tool = ToolDefinition("noop", "noop", {}, lambda: (True, "ok"))
        result = tool.execute(extra="unexpected")
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "INVALID_PARAMETERS")

    def test_legacy_failure_string_is_not_success(self):
        tool = ToolDefinition("open", "open", {}, lambda: "I could not open the application.")
        self.assertFalse(tool.execute()["success"])

    def test_exception_returns_safe_structured_failure(self):
        def fail():
            raise RuntimeError("private path should not be returned")
        result = ToolDefinition("failing_tool", "failure", {}, fail).execute()
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "TOOL_EXCEPTION")
        self.assertNotIn("private path", result["message"])


class OrchestratorPhase1Tests(unittest.TestCase):
    def test_fast_path_preserves_structured_result(self):
        registry = ToolRegistry()
        registry.register(
            "open_application", "launch app",
            {"application": {"type": "string"}},
            lambda application: (True, "Application opened"),
        )
        result = AgentOrchestrator(registry=registry).process_command("Open Notepad")
        self.assertTrue(result["success"])
        self.assertEqual(result["path"], "fast_path")
        self.assertIn("execution_time_ms", result)

    def test_unregistered_model_tool_fails_closed(self):
        orchestrator = AgentOrchestrator(registry=ToolRegistry())
        orchestrator._agentic_tool_selection = lambda command: {
            "tool": "run_arbitrary_command", "parameters": {}, "intent": "action"
        }
        result = orchestrator.process_command("do something")
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "UNKNOWN_TOOL")


if __name__ == "__main__":
    unittest.main()
