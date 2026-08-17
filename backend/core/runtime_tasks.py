import os
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone

from backend.core.checkpoint import load_checkpoint, save_checkpoint
from backend.core.dynamic_runtime import execute_dynamic_state, initialize_dynamic_state
from backend.core.human import request_review
from backend.core.policy import evaluate_human_policy
from backend.core.resume import resume_agent_loop
from backend.core.runtime_evaluator import evaluate_runtime_state
from backend.core.state import COMPLETED, FAILED, QUEUED, RUNNING, AgentState


_EXECUTOR = ThreadPoolExecutor(max_workers=int(os.getenv("RUNTIME_WORKERS", "2")))
_TASKS: dict[str, Future] = {}


def get_runtime_mode() -> str:
    mode = os.getenv("RUNTIME_MODE", "sync").strip().lower()
    return "async" if mode == "async" else "sync"


def is_async_runtime_enabled() -> bool:
    return get_runtime_mode() == "async"


def is_worker_initialized() -> bool:
    return _EXECUTOR is not None


def create_queued_dynamic_session(event: str, created_by: dict | None = None) -> AgentState:
    state = initialize_dynamic_state(event)
    state.set_status(QUEUED)
    state.metadata["runtime_mode"] = "async"
    state.metadata["queued_at"] = _now_iso()
    if created_by:
        state.metadata["created_by"] = {
            "id": created_by.get("id"),
            "username": created_by.get("username", ""),
            "role": created_by.get("role", ""),
        }
    save_checkpoint(state)
    return state


def submit_dynamic_session(session_id: str) -> Future:
    future = _EXECUTOR.submit(run_dynamic_session_task, session_id)
    _TASKS[session_id] = future
    return future


def submit_resume_session(session_id: str) -> Future:
    future = _EXECUTOR.submit(run_resume_session_task, session_id)
    _TASKS[session_id] = future
    return future


def get_task_status(session_id: str) -> str | None:
    future = _TASKS.get(session_id)
    if future is None:
        return None
    if future.running():
        return "running"
    if future.done():
        return "finished"
    return "queued"


def run_dynamic_session_task(session_id: str) -> dict:
    state = load_checkpoint(session_id)
    if state is None:
        return {
            "session_id": session_id,
            "status": "error",
            "error": "checkpoint_not_found",
        }
    try:
        state.set_status(RUNNING)
        save_checkpoint(state)
        result = execute_dynamic_state(state)
        evaluation = evaluate_runtime_state(state)
        policy = evaluate_human_policy(state, evaluation)
        state.metadata["evaluation"] = evaluation
        state.metadata["policy"] = policy

        if policy.get("required"):
            request_review(state, policy.get("reason", "Human review required."))
            status = "waiting_human"
        else:
            state.set_status(COMPLETED)
            status = "completed"

        save_checkpoint(state)
        return {
            **result,
            "status": status,
            "state_status": state.status,
            "approval": dict(state.approval),
            "evaluation": evaluation,
            "policy": policy,
        }
    except Exception as exc:  # pragma: no cover - exercised through integration tests.
        _mark_runtime_failed(state, exc)
        save_checkpoint(state)
        return {
            "session_id": state.session_id,
            "status": "failed",
            "state_status": state.status,
            "error": str(exc),
        }


def run_resume_session_task(session_id: str) -> dict:
    try:
        return resume_agent_loop(session_id)
    except Exception as exc:  # pragma: no cover - defensive worker guard.
        state = load_checkpoint(session_id)
        if state is not None:
            _mark_runtime_failed(state, exc)
            save_checkpoint(state)
        return {
            "session_id": session_id,
            "status": "failed",
            "error": str(exc),
        }


def run_dynamic_sync(event: str) -> dict:
    state = initialize_dynamic_state(event)
    result = execute_dynamic_state(state)
    evaluation = evaluate_runtime_state(state)
    policy = evaluate_human_policy(state, evaluation)
    state.metadata["evaluation"] = evaluation
    state.metadata["policy"] = policy

    if policy.get("required"):
        request_review(state, policy.get("reason", "Human review required."))
        status = "waiting_human"
    else:
        state.set_status(COMPLETED)
        status = "completed"

    save_checkpoint(state)
    return {
        **result,
        "status": status,
        "state_status": state.status,
        "approval": dict(state.approval),
        "evaluation": evaluation,
        "policy": policy,
    }


def _mark_runtime_failed(state: AgentState, exc: Exception) -> None:
    if state.status != FAILED:
        state.set_status(FAILED)
    timestamp = _now_iso()
    state.add_trace(
        {
            "agent": "runtime_worker",
            "reason": "Background dynamic runtime failed.",
            "start_time": timestamp,
            "end_time": timestamp,
            "status": "failed",
            "output": {},
            "error": str(exc),
        }
    )
    state.mark_failed("runtime_worker", str(exc))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
