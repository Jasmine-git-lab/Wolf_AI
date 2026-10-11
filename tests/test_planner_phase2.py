"""Tests for Wolf AI Phase 2 sequential execution."""

import unittest

from backend.executor import TaskExecutor
from backend.planner import TaskPlan, StepStatus
from backend.registry import ToolRegistry


class TaskExecutorPhase2Tests(unittest.TestCase):

    def test_multiple_steps_execute_in_order(self):

        calls = []

        registry = ToolRegistry()

        registry.register(
            "first",
            "First test tool",
            {},
            lambda: (
                calls.append("first"),
                True,
            )[1:] if False else (
                True,
                calls.append("first") or "first done",
            ),
        )

        registry.register(
            "second",
            "Second test tool",
            {},
            lambda: (
                True,
                calls.append("second") or "second done",
            ),
        )

        plan = TaskPlan(
            goal="Run two steps"
        )

        plan.add_step("first")
        plan.add_step("second")

        result = TaskExecutor(
            registry
        ).execute_plan(plan)

        self.assertTrue(result["success"])
        self.assertEqual(
            calls,
            ["first", "second"],
        )

        self.assertEqual(
            plan.steps[0].status,
            StepStatus.SUCCESS,
        )

        self.assertEqual(
            plan.steps[1].status,
            StepStatus.SUCCESS,
        )

    def test_failed_step_stops_later_steps(self):

        calls = []

        registry = ToolRegistry()

        def fail():
            calls.append("fail")
            return (
                False,
                "The operation failed.",
            )

        def should_not_run():
            calls.append("later")
            return (
                True,
                "Should not run.",
            )

        registry.register(
            "fail",
            "Failing tool",
            {},
            fail,
        )

        registry.register(
            "later",
            "Later tool",
            {},
            should_not_run,
        )

        plan = TaskPlan(
            goal="Test partial failure"
        )

        plan.add_step("fail")
        plan.add_step("later")

        result = TaskExecutor(
            registry
        ).execute_plan(plan)

        self.assertFalse(result["success"])
        self.assertEqual(
            calls,
            ["fail"],
        )

        self.assertEqual(
            plan.steps[0].status,
            StepStatus.FAILED,
        )

        self.assertEqual(
            plan.steps[1].status,
            StepStatus.PENDING,
        )

    def test_step_result_is_saved_to_context(self):

        registry = ToolRegistry()

        registry.register(
            "create",
            "Create something",
            {},
            lambda: (
                True,
                "Created successfully.",
            ),
        )

        plan = TaskPlan(
            goal="Context test"
        )

        step = plan.add_step(
            "create"
        )

        result = TaskExecutor(
            registry
        ).execute_plan(plan)

        self.assertTrue(result["success"])

        saved = plan.get_context(
            f"step_{step.id}"
        )

        self.assertIsNotNone(saved)
        self.assertTrue(
            saved["success"]
        )

    def test_unknown_tool_fails_safely(self):

        registry = ToolRegistry()

        plan = TaskPlan(
            goal="Unknown tool test"
        )

        plan.add_step(
            "unknown_tool"
        )

        result = TaskExecutor(
            registry
        ).execute_plan(plan)

        self.assertFalse(result["success"])

    def test_retry_is_bounded(self):

        attempts = []

        registry = ToolRegistry()

        def temporary_failure():

            attempts.append(1)

            return {
                "success": False,
                "ok": False,
                "error_code": "TEMPORARY_FAILURE",
                "message": "Temporary failure.",
                "tool": "temporary",
                "data": None,
            }

        registry.register(
            "temporary",
            "Temporary failure",
            {},
            temporary_failure,
        )

        plan = TaskPlan(
            goal="Retry test"
        )

        step = plan.add_step(
            "temporary"
        )

        step.max_retries = 2

        result = TaskExecutor(
            registry
        ).execute_plan(plan)

        self.assertFalse(result["success"])

        # Initial attempt + 2 retries.
        self.assertEqual(
            len(attempts),
            3,
        )

        self.assertEqual(
            step.retry_count,
            2,
        )


if __name__ == "__main__":
    unittest.main()