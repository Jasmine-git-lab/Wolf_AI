"""
Wolf AI - Phase 2 Sequential Task Executor

Responsible for:
- Sequential task execution
- Safe tool execution through ToolRegistry
- Bounded retries
- Step verification
- Short-term plan context
- Safe failure handling

Important:
A failed step must NEVER become a successful plan.
"""

import logging
import time
import re
from typing import Any, Callable, Dict, Optional

from backend.planner import TaskPlan, TaskStep
from backend.registry import ToolRegistry


logger = logging.getLogger("wolf.executor")


VerificationFunction = Callable[
    [TaskStep, Dict[str, Any]],
    Dict[str, Any],
]


class TaskExecutor:
    """
    Executes TaskPlan objects sequentially.

    Example:

        Step 1 -> execute -> verify -> success
        Step 2 -> execute -> verify -> success
        Step 3 -> execute -> verify -> success

    If a step permanently fails:

        Step 1 -> success
        Step 2 -> FAILED
        Step 3 -> NOT EXECUTED
    """

    def __init__(
        self,
        registry: ToolRegistry,
        verifiers: Optional[
            Dict[str, VerificationFunction]
        ] = None,
    ):
        self.registry = registry
        self.verifiers = verifiers or {}

    # =========================================================
    # PUBLIC API
    # =========================================================

    def execute_plan(
        self,
        plan: TaskPlan,
    ) -> Dict[str, Any]:
        """
        Execute all plan steps sequentially.

        Returns a structured result.

        Success:
            {
                "success": True,
                "status": "success",
                ...
            }

        Failure:
            {
                "success": False,
                "status": "failed",
                ...
            }
        """

        started = time.perf_counter()

        plan.status = "running"

        logger.info(
            "Starting plan %s: %s",
            plan.id,
            plan.goal,
        )

        while True:

            # -------------------------------------------------
            # GET CURRENT STEP
            # -------------------------------------------------

            step = plan.current_step()

            # No more steps.
            if step is None:
                break

            # -------------------------------------------------
            # EXECUTE CURRENT STEP
            # -------------------------------------------------

            result = self._execute_step(
                plan,
                step,
            )

            # -------------------------------------------------
            # IMPORTANT:
            # A step result is successful ONLY when the
            # returned dictionary explicitly says success=True.
            # -------------------------------------------------

            if not isinstance(result, dict):
                result = {
                    "success": False,
                    "ok": False,
                    "error_code": "INVALID_EXECUTION_RESULT",
                    "message": (
                        "Executor received an invalid "
                        "result from the step."
                    ),
                    "tool": step.tool,
                    "data": None,
                }

            if result.get("success") is not True:

                elapsed = (
                    time.perf_counter() - started
                ) * 1000

                # Explicitly mark plan as failed.
                plan.status = "failed"

                logger.error(
                    "Plan %s failed at step %s",
                    plan.id,
                    step.id,
                )

                return {
                    "success": False,
                    "ok": False,
                    "status": "failed",
                    "plan_id": plan.id,
                    "goal": plan.goal,
                    "failed_step": step.id,
                    "message": (
                        f"Task stopped at step "
                        f"{step.id}: "
                        f"{result.get(
                            'message',
                            'Step failed.'
                        )}"
                    ),
                    "steps": [
                        s.to_dict()
                        for s in plan.steps
                    ],
                    "context": dict(plan.context),
                    "execution_time_ms": round(
                        elapsed,
                        2,
                    ),
                }

            # -------------------------------------------------
            # CURRENT STEP SUCCESSFUL
            # -------------------------------------------------

            logger.info(
                "Step %s completed successfully.",
                step.id,
            )

            # Move to next step.
            advanced = plan.advance()

            if not advanced:
                break

        # =====================================================
        # ALL STEPS SUCCESSFUL
        # =====================================================

        plan.mark_complete()

        elapsed = (
            time.perf_counter() - started
        ) * 1000

        logger.info(
            "Plan %s completed successfully.",
            plan.id,
        )

        return {
            "success": True,
            "ok": True,
            "status": "success",
            "plan_id": plan.id,
            "goal": plan.goal,
            "message": (
                "All planned steps completed successfully."
            ),
            "steps": [
                s.to_dict()
                for s in plan.steps
            ],
            "context": dict(plan.context),
            "execution_time_ms": round(
                elapsed,
                2,
            ),
        }

    # =========================================================
    # SINGLE STEP EXECUTION
    # =========================================================

    def _execute_step(
        self,
        plan: TaskPlan,
        step: TaskStep,
    ) -> Dict[str, Any]:
        """
        Execute one step.

        Retry logic is explicit:

            max_retries = 2

            attempt 1
            attempt 2
            attempt 3

        Therefore max_retries means the number of
        RETRIES AFTER THE INITIAL ATTEMPT.
        """

        step.mark_running()

        # Number of actual tool executions.
        attempt = 0

        # Maximum number of executions.
        max_attempts = step.max_retries + 1

        last_result: Dict[str, Any] = {}

        while attempt < max_attempts:

            attempt += 1

            logger.info(
                "Executing step %s "
                "(attempt %s/%s)",
                step.id,
                attempt,
                max_attempts,
            )

            # -------------------------------------------------
            # ALWAYS EXECUTE THROUGH TOOL REGISTRY WITH CONTEXT
            # -------------------------------------------------

            resolved_params = self._resolve_parameters(
                step.parameters,
                plan.context,
            )

            try:

                result = self.registry.execute(
                    step.tool,
                    **resolved_params,
                )

            except Exception as exc:

                logger.exception(
                    "Unexpected executor error "
                    "for step %s",
                    step.id,
                )

                result = {
                    "success": False,
                    "ok": False,
                    "error_code": "TOOL_EXCEPTION",
                    "message": (
                        f"Tool execution failed: {exc}"
                    ),
                    "tool": step.tool,
                    "data": None,
                }

            # -------------------------------------------------
            # NORMALIZE INVALID RESULTS
            # -------------------------------------------------

            if not isinstance(result, dict):

                result = {
                    "success": False,
                    "ok": False,
                    "error_code": "INVALID_EXECUTION_RESULT",
                    "message": (
                        "Tool returned an invalid "
                        "execution result."
                    ),
                    "tool": step.tool,
                    "data": None,
                }

            last_result = result

            # -------------------------------------------------
            # TOOL SUCCESS
            # -------------------------------------------------

            if result.get("success") is True:

                verification = self._verify(
                    step,
                    result,
                )

                step.verification = verification

                # ---------------------------------------------
                # VERIFICATION SUCCESS
                # ---------------------------------------------

                if verification.get("success") is True:

                    step.mark_success(
                        result
                    )

                    plan.store_context(
                        f"step_{step.id}",
                        result,
                    )

                    plan.store_context(
                        "last",
                        result,
                    )

                    return result

                # ---------------------------------------------
                # VERIFICATION FAILURE
                # ---------------------------------------------

                verification_failure = {
                    "success": False,
                    "ok": False,
                    "error_code": (
                        "VERIFICATION_FAILED"
                    ),
                    "message": (
                        verification.get(
                            "message",
                            "Step verification failed.",
                        )
                    ),
                    "tool": step.tool,
                    "data": result.get(
                        "data"
                    ),
                }

                last_result = verification_failure

                logger.warning(
                    "Verification failed for "
                    "step %s.",
                    step.id,
                )

                # Retry if another attempt is available.
                if (
                    attempt < max_attempts
                    and self._is_retryable(
                        verification_failure
                    )
                ):

                    step.register_retry()

                    logger.warning(
                        "Retrying step %s "
                        "after verification failure "
                        "(retry %s/%s).",
                        step.id,
                        step.retry_count,
                        step.max_retries,
                    )

                    continue

                # No attempts remaining.
                step.mark_failed(
                    verification_failure
                )

                plan.store_context(
                    f"step_{step.id}",
                    verification_failure,
                )

                return verification_failure

            # -------------------------------------------------
            # TOOL FAILURE
            # -------------------------------------------------

            logger.warning(
                "Step %s failed on attempt %s/%s: %s",
                step.id,
                attempt,
                max_attempts,
                result.get(
                    "message",
                    "Unknown failure.",
                ),
            )

            # -------------------------------------------------
            # RETRYABLE FAILURE
            # -------------------------------------------------

            if (
                attempt < max_attempts
                and self._is_retryable(result)
            ):

                step.register_retry()

                logger.warning(
                    "Retrying step %s "
                    "(retry %s/%s).",
                    step.id,
                    step.retry_count,
                    step.max_retries,
                )

                continue

            # -------------------------------------------------
            # FINAL FAILURE
            # -------------------------------------------------

            step.mark_failed(
                result
            )

            plan.store_context(
                f"step_{step.id}",
                result,
            )

            return result

        # =====================================================
        # SAFETY FALLBACK
        # =====================================================

        # This should normally never be reached because the
        # loop returns on success or final failure.

        fallback = {
            "success": False,
            "ok": False,
            "error_code": "EXECUTION_ABORTED",
            "message": (
                "Step execution ended unexpectedly."
            ),
            "tool": step.tool,
            "data": last_result,
        }

        step.mark_failed(
            fallback
        )

        plan.store_context(
            f"step_{step.id}",
            fallback,
        )

        return fallback

    # =========================================================
    # VERIFICATION
    # =========================================================

    def _verify(
        self,
        step: TaskStep,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Verify successful tool execution.

        If a custom verifier exists for the tool,
        use it.

        Otherwise use the tool's own structured
        success response.
        """

        verifier = self.verifiers.get(
            step.tool
        )

        # -----------------------------------------------------
        # NO CUSTOM VERIFIER
        # -----------------------------------------------------

        if verifier is None:

            return {
                "success": (
                    result.get("success") is True
                ),
                "message": (
                    "Tool reported successful execution."
                ),
            }

        # -----------------------------------------------------
        # CUSTOM VERIFIER
        # -----------------------------------------------------

        try:

            verification = verifier(
                step,
                result,
            )

            if not isinstance(
                verification,
                dict,
            ):

                return {
                    "success": False,
                    "message": (
                        "Verifier returned an "
                        "invalid result."
                    ),
                }

            return verification

        except Exception as exc:

            logger.exception(
                "Verifier failed for tool %s.",
                step.tool,
            )

            return {
                "success": False,
                "message": (
                    "Verification could not "
                    "be completed."
                ),
                "error": str(exc),
            }

    # =========================================================
    # RETRY POLICY
    # =========================================================

    @staticmethod
    def _is_retryable(
        result: Dict[str, Any],
    ) -> bool:
        """
        Decide whether a failed operation may be retried.

        Retryable:
            TOOL_EXCEPTION
            VERIFICATION_FAILED
            TEMPORARY_FAILURE

        Not retryable:
            INVALID_PARAMETERS
            unknown tool
            explicit input errors
            other permanent failures
        """

        error_code = result.get(
            "error_code",
            "",
        )

        return error_code in {
            "TOOL_EXCEPTION",
            "VERIFICATION_FAILED",
            "TEMPORARY_FAILURE",
        }

    # =========================================================
    # PARAMETER CONTEXT RESOLUTION
    # =========================================================

    @staticmethod
    def _resolve_parameters(
        parameters: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Resolves template expressions in parameters using context data.
        e.g. "{{last.data.path}}" or "{{step_1.data.content}}"
        """
        resolved: Dict[str, Any] = {}
        for k, v in (parameters or {}).items():
            if isinstance(v, str) and "{{" in v and "}}" in v:
                pattern = r"\{\{\s*([a-zA-Z0-9_\.]+)\s*\}\}"
                def replacer(match):
                    expr = match.group(1).strip()
                    parts = expr.split(".")
                    cur = context
                    for part in parts:
                        if isinstance(cur, dict) and part in cur:
                            cur = cur[part]
                        else:
                            return match.group(0)
                    return str(cur)
                resolved[k] = re.sub(pattern, replacer, v)
            else:
                resolved[k] = v
        return resolved