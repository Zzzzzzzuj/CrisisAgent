from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import asdict, dataclass, field
from time import monotonic
from typing import Any, Callable

from backend.skills.registry import SkillRegistry, validate_json_schema_payload
from backend.skills.execution_budget import (
    TOOL_BUDGET_EXCEEDED,
    TOOL_LOOP_DETECTED,
    TOOL_RETRY_BUDGET_EXCEEDED,
    TOOL_RUNTIME_BUDGET_EXCEEDED,
    ToolExecutionBudget,
)


TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
TOOL_DISABLED = "TOOL_DISABLED"
TOOL_INPUT_INVALID = "TOOL_INPUT_INVALID"
TOOL_OUTPUT_INVALID = "TOOL_OUTPUT_INVALID"
TOOL_TIMEOUT = "TOOL_TIMEOUT"
TOOL_RETRY_EXHAUSTED = "TOOL_RETRY_EXHAUSTED"
TOOL_EXECUTION_FAILED = "TOOL_EXECUTION_FAILED"
TOOL_POLICY_DENIED = "TOOL_POLICY_DENIED"
TOOL_FALLBACK_FAILED = "TOOL_FALLBACK_FAILED"


@dataclass(frozen=True)
class ToolResult:
    tool_name: str
    success: bool
    output: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    attempts: int = 0
    retry_count: int = 0
    fallback_used: bool = False
    human_review_required: bool = False
    trace: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ToolRunner:
    """Standalone, deterministic tool execution wrapper for the experiment path."""

    def __init__(
        self,
        registry: SkillRegistry,
        fallback_handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] | None = None,
        policy_checker: Callable[[Any, dict[str, Any]], tuple[bool, str]] | None = None,
        budget: ToolExecutionBudget | None = None,
    ):
        self.registry = registry
        self.fallback_handlers = fallback_handlers or {}
        self.policy_checker = policy_checker
        self.budget = budget or ToolExecutionBudget()

    def run(
        self,
        tool_name: str,
        payload: dict[str, Any],
        *,
        human_confirmation: bool = False,
    ) -> ToolResult:
        started = monotonic()
        try:
            definition = self.registry.get(tool_name)
        except KeyError as exc:
            return self._result(tool_name, started, error_code=TOOL_NOT_FOUND, error_message=str(exc))

        if not definition.enabled:
            return self._result(tool_name, started, error_code=TOOL_DISABLED, error_message="Tool is disabled.")

        if definition.requires_human_confirmation and not human_confirmation:
            return self._result(
                tool_name,
                started,
                error_code=TOOL_POLICY_DENIED,
                error_message="Tool requires human confirmation.",
                human_review_required=True,
            )

        if self.policy_checker is not None:
            allowed, reason = self.policy_checker(definition, payload)
            if not allowed:
                return self._result(
                    tool_name,
                    started,
                    error_code=TOOL_POLICY_DENIED,
                    error_message=reason,
                    human_review_required=True,
                )

        try:
            validated_payload = self.registry.validate_input(tool_name, payload)
        except Exception as exc:
            return self._result(tool_name, started, error_code=TOOL_INPUT_INVALID, error_message=str(exc))

        max_retries = max(0, int(definition.max_retries))
        attempts = 0
        last_code = TOOL_EXECUTION_FAILED
        last_message = "Tool execution failed."

        while attempts <= max_retries:
            attempts += 1
            budget_check = self.budget.check(tool_name, validated_payload, attempt=attempts)
            if not budget_check.allowed:
                return self._result(
                    tool_name,
                    started,
                    error_code=budget_check.error_code,
                    error_message=budget_check.reason,
                    attempts=attempts - 1,
                    retry_count=max(0, attempts - 2),
                    human_review_required=budget_check.human_review_required,
                    budget_trace=budget_check.trace,
                )
            self.budget.record(
                tool_name,
                validated_payload,
                step_index=budget_check.trace["step_index"],
                attempt=attempts,
            )
            try:
                output = self._execute_with_timeout(definition.handler, validated_payload, definition.timeout_ms)
                if not isinstance(output, dict):
                    raise _ToolFailure(TOOL_OUTPUT_INVALID, "Tool output must be a JSON object.")
                try:
                    validate_json_schema_payload(definition.output_schema, output)
                except Exception as exc:
                    raise _ToolFailure(TOOL_OUTPUT_INVALID, str(exc)) from exc
                return self._result(
                    tool_name,
                    started,
                    success=True,
                    output=output,
                    attempts=attempts,
                    retry_count=attempts - 1,
                )
            except _ToolFailure as exc:
                last_code, last_message = exc.error_code, str(exc)
            except FutureTimeoutError:
                last_code, last_message = TOOL_TIMEOUT, "Tool execution timed out."
            except Exception as exc:
                last_code, last_message = TOOL_EXECUTION_FAILED, str(exc)

        if max_retries > 0 and last_code in {TOOL_TIMEOUT, TOOL_EXECUTION_FAILED}:
            last_code = TOOL_RETRY_EXHAUSTED

        fallback = self._try_fallback(definition, validated_payload, started, attempts, last_code, last_message)
        if fallback is not None:
            return fallback

        return self._result(
            tool_name,
            started,
            error_code=last_code,
            error_message=last_message,
            attempts=attempts,
            retry_count=max(0, attempts - 1),
            human_review_required=True,
        )

    @staticmethod
    def _execute_with_timeout(handler, payload, timeout_ms: int):
        if handler is None:
            raise _ToolFailure(TOOL_EXECUTION_FAILED, "Tool handler is missing.")
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(handler, payload)
            return future.result(timeout=max(1, int(timeout_ms)) / 1000)

    def _try_fallback(self, definition, payload, started, attempts, error_code, error_message):
        if definition.fallback_policy == "none":
            return None
        handler = self.fallback_handlers.get(definition.name)
        if handler is None:
            return self._result(
                definition.name,
                started,
                error_code=TOOL_FALLBACK_FAILED,
                error_message="Fallback handler is missing.",
                attempts=attempts,
                retry_count=max(0, attempts - 1),
                human_review_required=True,
            )
        try:
            output = handler(payload)
            if not isinstance(output, dict):
                raise ValueError("Fallback output must be a JSON object.")
            validate_json_schema_payload(definition.output_schema, output)
            return self._result(
                definition.name,
                started,
                success=True,
                output=output,
                attempts=attempts,
                retry_count=max(0, attempts - 1),
                fallback_used=True,
            )
        except Exception as exc:
            return self._result(
                definition.name,
                started,
                error_code=TOOL_FALLBACK_FAILED,
                error_message=str(exc),
                attempts=attempts,
                retry_count=max(0, attempts - 1),
                fallback_used=True,
                human_review_required=True,
            )

    @staticmethod
    def _result(tool_name, started, *, success=False, output=None, error_code=None, error_message=None, attempts=0, retry_count=0, fallback_used=False, human_review_required=False, budget_trace=None):
        duration_ms = round((monotonic() - started) * 1000, 2)
        trace = {
            "tool_name": tool_name,
            "attempts": attempts,
            "retry_count": retry_count,
            "duration_ms": duration_ms,
            "error_code": error_code,
            "fallback_used": fallback_used,
            "success": success,
        }
        if budget_trace:
            trace.update(budget_trace)
        return ToolResult(
            tool_name=tool_name,
            success=success,
            output=output or {},
            error_code=error_code,
            error_message=error_message,
            attempts=attempts,
            retry_count=retry_count,
            fallback_used=fallback_used,
            human_review_required=human_review_required,
            trace=trace,
        )


class _ToolFailure(Exception):
    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code
