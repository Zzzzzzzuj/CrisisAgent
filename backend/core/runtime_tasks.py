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
_RQ_JOBS: dict[str, object] = {}


def get_runtime_mode() -> str:
    mode = os.getenv("RUNTIME_MODE", "sync").strip().lower()
    return "async" if mode == "async" else "sync"


def is_async_runtime_enabled() -> bool:
    return get_runtime_mode() == "async"


def is_worker_initialized() -> bool:
    if get_task_queue_backend() == "rq":
        return _is_rq_configured()
    return _EXECUTOR is not None


def get_task_queue_backend() -> str:
    backend = os.getenv("TASK_QUEUE_BACKEND", "inprocess").strip().lower()
    return "rq" if backend == "rq" else "inprocess"


def get_redis_url() -> str:
    return os.getenv("REDIS_URL", "redis://localhost:6379/0").strip()


def get_rq_queue_name() -> str:
    return os.getenv("RQ_QUEUE_NAME", "crisisagent").strip() or "crisisagent"


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


def submit_dynamic_session(session_id: str):
    if get_task_queue_backend() == "rq":
        job = _enqueue_rq_task(
            "backend.core.runtime_tasks.run_dynamic_session_task",
            session_id,
            job_prefix="dynamic",
        )
        _RQ_JOBS[session_id] = job
        return job
    future = _EXECUTOR.submit(run_dynamic_session_task, session_id)
    _TASKS[session_id] = future
    return future


def submit_resume_session(session_id: str):
    if get_task_queue_backend() == "rq":
        job = _enqueue_rq_task(
            "backend.core.runtime_tasks.run_resume_session_task",
            session_id,
            job_prefix="resume",
        )
        _RQ_JOBS[session_id] = job
        return job
    future = _EXECUTOR.submit(run_resume_session_task, session_id)
    _TASKS[session_id] = future
    return future


def get_task_status(session_id: str) -> str | None:
    if get_task_queue_backend() == "rq":
        job = _RQ_JOBS.get(session_id)
        if job is None:
            return None
        try:
            return str(job.get_status(refresh=True))
        except TypeError:
            return str(job.get_status())

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


def _enqueue_rq_task(func_path: str, session_id: str, job_prefix: str):
    queue = get_rq_queue()
    timeout = int(os.getenv("RQ_JOB_TIMEOUT_SECONDS", "900"))
    return queue.enqueue(
        func_path,
        session_id,
        job_timeout=timeout,
        meta={"session_id": session_id, "task_type": job_prefix},
    )


def get_rq_queue():
    redis_connection = get_redis_connection()
    try:
        from rq import Queue
    except ImportError as exc:  # pragma: no cover - covered through readiness/config tests.
        raise RuntimeError("RQ backend requires the 'rq' package. Run: pip install -r requirements.txt") from exc

    return Queue(get_rq_queue_name(), connection=redis_connection)


def get_redis_connection():
    try:
        from redis import Redis
    except ImportError as exc:  # pragma: no cover - covered through readiness/config tests.
        raise RuntimeError("RQ backend requires the 'redis' package. Run: pip install -r requirements.txt") from exc

    return Redis.from_url(get_redis_url())


def check_rq_backend() -> dict:
    if get_task_queue_backend() != "rq":
        return {
            "ok": True,
            "backend": "inprocess",
            "queue_name": None,
            "redis_url_configured": False,
        }

    try:
        connection = get_redis_connection()
        connection.ping()
        return {
            "ok": True,
            "backend": "rq",
            "queue_name": get_rq_queue_name(),
            "redis_url_configured": bool(get_redis_url()),
        }
    except Exception as exc:
        return {
            "ok": False,
            "backend": "rq",
            "queue_name": get_rq_queue_name(),
            "redis_url_configured": bool(get_redis_url()),
            "error": exc.__class__.__name__,
        }


def _is_rq_configured() -> bool:
    return check_rq_backend().get("ok") is True
