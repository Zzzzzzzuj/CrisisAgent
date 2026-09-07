from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable


TOOL_BUDGET_EXCEEDED = "TOOL_BUDGET_EXCEEDED"
TOOL_RETRY_BUDGET_EXCEEDED = "TOOL_RETRY_BUDGET_EXCEEDED"
TOOL_RUNTIME_BUDGET_EXCEEDED = "TOOL_RUNTIME_BUDGET_EXCEEDED"
TOOL_LOOP_DETECTED = "TOOL_LOOP_DETECTED"


@dataclass(frozen=True)
class ToolExecutionBudget:
    max_steps: int = 6
    max_retries: int = 1
    max_runtime_ms: int = 5000
    max_same_call: int = 1
    started_at_ms: float = field(default_factory=lambda: time.monotonic() * 1000, compare=False)
    records: list["ToolCallRecord"] = field(default_factory=list, compare=False)
    _clock_ms: Callable[[], float] = field(default=lambda: time.monotonic() * 1000, compare=False, repr=False)

    def __post_init__(self):
        if self.max_steps <= 0 or self.max_retries < 0 or self.max_runtime_ms <= 0 or self.max_same_call <= 0:
            raise ValueError("Execution budget limits must be positive, except max_retries which may be zero.")

    def check(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        attempt: int = 1,
        now_ms: float | None = None,
    ) -> "BudgetCheckResult":
        now = self._clock_ms() if now_ms is None else now_ms
        normalized_hash = normalized_arguments_hash(arguments)
        logical_steps = sum(1 for record in self.records if record.attempt == 1)
        retries = sum(1 for record in self.records if record.attempt > 1)
        same_calls = sum(
            1
            for record in self.records
            if record.tool_name == tool_name and record.normalized_arguments_hash == normalized_hash
        )
        elapsed = max(0.0, now - self.started_at_ms)
        trace = {
            "budget_max_steps": self.max_steps,
            "budget_max_retries": self.max_retries,
            "budget_max_runtime_ms": self.max_runtime_ms,
            "budget_max_same_call": self.max_same_call,
            "budget_steps_used": logical_steps,
            "budget_retries_used": retries,
            "budget_same_call_count": same_calls,
            "budget_elapsed_runtime_ms": round(elapsed, 2),
            "normalized_arguments_hash": normalized_hash,
            "step_index": logical_steps + (1 if attempt == 1 else 0),
            "attempt": attempt,
        }

        if elapsed > self.max_runtime_ms:
            return BudgetCheckResult(False, "Runtime budget exceeded.", TOOL_RUNTIME_BUDGET_EXCEEDED, True, trace)
        if attempt > 1 and retries >= self.max_retries:
            return BudgetCheckResult(False, "Retry budget exceeded.", TOOL_RETRY_BUDGET_EXCEEDED, True, trace)
        if attempt == 1 and logical_steps >= self.max_steps:
            return BudgetCheckResult(False, "Step budget exceeded.", TOOL_BUDGET_EXCEEDED, True, trace)
        if attempt == 1 and same_calls >= self.max_same_call:
            return BudgetCheckResult(False, "Repeated tool call detected.", TOOL_LOOP_DETECTED, True, trace)
        return BudgetCheckResult(True, "Budget allows execution.", None, False, trace)

    def record(self, tool_name: str, arguments: dict[str, Any], step_index: int, attempt: int) -> "ToolCallRecord":
        record = ToolCallRecord(
            tool_name=tool_name,
            normalized_arguments_hash=normalized_arguments_hash(arguments),
            step_index=step_index,
            attempt=attempt,
            timestamp_ms=int(time.time() * 1000),
        )
        self.records.append(record)
        return record


@dataclass(frozen=True)
class ToolCallRecord:
    tool_name: str
    normalized_arguments_hash: str
    step_index: int
    attempt: int
    timestamp_ms: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BudgetCheckResult:
    allowed: bool
    reason: str
    error_code: str | None
    human_review_required: bool
    trace: dict[str, Any]


def normalized_arguments_hash(arguments: dict[str, Any]) -> str:
    normalized = json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
