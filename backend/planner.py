"""
Wolf AI - Phase 2 Planning Engine

Represents multi-step tasks as structured plans.
This module does not execute tools.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class TaskStep:
    """
    One executable step inside a task plan.
    """

    tool: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    description: str = ""

    id: str = field(default_factory=lambda: uuid4().hex[:8])
    status: StepStatus = StepStatus.PENDING

    result: Optional[Dict[str, Any]] = None
    verification: Optional[Dict[str, Any]] = None

    retry_count: int = 0
    max_retries: int = 2

    def mark_running(self) -> None:
        self.status = StepStatus.RUNNING

    def mark_success(
        self,
        result: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.status = StepStatus.SUCCESS
        self.result = result

    def mark_failed(
        self,
        result: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.status = StepStatus.FAILED
        self.result = result

    def mark_skipped(self) -> None:
        self.status = StepStatus.SKIPPED

    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries

    def register_retry(self) -> None:
        self.retry_count += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tool": self.tool,
            "parameters": self.parameters,
            "description": self.description,
            "status": self.status.value,
            "result": self.result,
            "verification": self.verification,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
        }


@dataclass
class TaskPlan:
    """
    Structured representation of a complete user task.
    """

    goal: str
    steps: List[TaskStep] = field(default_factory=list)

    id: str = field(default_factory=lambda: uuid4().hex[:8])

    status: str = "pending"
    current_step_index: int = 0

    context: Dict[str, Any] = field(default_factory=dict)

    def add_step(
        self,
        tool: str,
        parameters: Optional[Dict[str, Any]] = None,
        description: str = "",
    ) -> TaskStep:

        step = TaskStep(
            tool=tool,
            parameters=parameters or {},
            description=description,
        )

        self.steps.append(step)
        return step

    def current_step(self) -> Optional[TaskStep]:
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]

        return None

    def advance(self) -> bool:
        """
        Move to the next step.

        Returns True if another step exists.
        """

        self.current_step_index += 1

        return self.current_step_index < len(self.steps)

    def is_complete(self) -> bool:
        return (
            len(self.steps) > 0
            and all(
                step.status
                in {
                    StepStatus.SUCCESS,
                    StepStatus.SKIPPED,
                }
                for step in self.steps
            )
        )

    def has_failed(self) -> bool:
        return any(
            step.status == StepStatus.FAILED
            for step in self.steps
        )

    def mark_complete(self) -> None:
        self.status = "failed" if self.has_failed() else "success"

    def store_context(
        self,
        key: str,
        value: Any,
    ) -> None:
        """
        Store short-term information produced by a step.
        """

        self.context[key] = value

    def get_context(
        self,
        key: str,
        default: Any = None,
    ) -> Any:

        return self.context.get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "goal": self.goal,
            "status": self.status,
            "current_step_index": self.current_step_index,
            "context": self.context,
            "steps": [
                step.to_dict()
                for step in self.steps
            ],
        }