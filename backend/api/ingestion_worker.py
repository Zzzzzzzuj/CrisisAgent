from __future__ import annotations

from typing import Any

from backend.api.ingestion_execution import execute_ingestion_payload, now
from backend.api.ingestion_heartbeat import current_worker_id, update_worker_heartbeat
from backend.api.ingestion_queue import IngestionQueueUnavailable, enqueue_dead_letter, reliability_settings, schedule_ingestion_retry
from backend.api.ingestion_run_store import get_ingestion_run_store
from backend.api.workspace_security import write_audit


TERMINAL_STATUSES = {"completed", "partial", "failed", "dry_run"}


def run_ingestion_job(run_id: str, payload: dict[str, Any], user_context: dict[str, Any]) -> dict[str, Any]:
    """RQ worker entry point. IngestionRun storage remains the source of truth."""
    store = get_ingestion_run_store()
    run = store.get(run_id)
    if run is None:
        return {"run_id": run_id, "status": "missing"}
    if run.get("status") != "queued":
        return {"run_id": run_id, "status": run.get("status"), "skipped": True}

    worker_id = current_worker_id()
    _, queue_name, _ = reliability_settings()
    _heartbeat_safely(worker_id, queue_name, "running")
    store.update(run_id, {"status": "running", "started_at": now(), "error": None, "worker_id": worker_id, "heartbeat_at": now(), "last_attempt_at": now()})
    write_audit(
        user_context,
        "ingestion.run.started",
        "ingestion_run",
        run_id,
        metadata={"execution_mode": "background", "queue_backend": "redis", "background": True, "worker_id": worker_id},
    )
    try:
        result = execute_ingestion_payload(payload)
        final_status = result["status"]
        updated = store.update(run_id, {**result, "execution_mode": "background", "queue_backend": "redis", "worker_id": worker_id, "heartbeat_at": now()})
        write_audit(
            user_context,
            "ingestion.run.completed",
            "ingestion_run",
            run_id,
            metadata={
                "execution_mode": "background",
                "queue_backend": "redis",
                "background": True,
                "job_id": updated.get("job_id"),
                "final_status": final_status,
            },
        )
        return updated
    except Exception as exc:
        return _handle_failure(store, run, run_id, payload, user_context, worker_id, exc)
    finally:
        _heartbeat_safely(worker_id, queue_name, "idle")


def _handle_failure(store, original_run: dict[str, Any], run_id: str, payload: dict[str, Any], user_context: dict[str, Any], worker_id: str, exc: Exception) -> dict[str, Any]:
    error = str(exc)
    retry_count = int(original_run.get("retry_count", 0)) + 1
    max_retries = int(original_run.get("max_retries", reliability_settings()[0]))
    is_timeout = exc.__class__.__name__ in {"JobTimeoutException", "TimeoutError"}
    if is_timeout:
        write_audit(
            user_context,
            "ingestion.run.timeout",
            "ingestion_run",
            run_id,
            "failed",
            error,
            {"worker_id": worker_id, "timeout_seconds": original_run.get("timeout_seconds")},
        )
    write_audit(user_context, "ingestion.run.failed", "ingestion_run", run_id, "failed", error, {"worker_id": worker_id, "retry_count": retry_count, "max_retries": max_retries})
    if retry_count <= max_retries:
        _, delay_seconds, _ = reliability_settings()
        updated = store.update(run_id, {"status": "queued", "retry_count": retry_count, "last_error": error, "error": error, "last_attempt_at": now(), "next_retry_at": now(), "worker_id": worker_id, "heartbeat_at": now(), "recovery_reason": "retry_scheduled"})
        try:
            job_id = schedule_ingestion_retry(run_id, payload, user_context, delay_seconds)
            updated = store.update(run_id, {"job_id": job_id})
            write_audit(user_context, "ingestion.run.retry_scheduled", "ingestion_run", run_id, metadata={"retry_count": retry_count, "max_retries": max_retries, "job_id": job_id})
            return updated
        except IngestionQueueUnavailable as queue_exc:
            error = f"{error}; retry enqueue failed: {queue_exc}"

    dead_lettered_at = now()
    updated = store.update(run_id, {"status": "failed", "finished_at": dead_lettered_at, "retry_count": retry_count, "last_error": error, "error": error, "dead_lettered_at": dead_lettered_at, "worker_id": worker_id, "heartbeat_at": now(), "recovery_reason": "retry_exhausted"})
    try:
        enqueue_dead_letter(run_id, error)
    except IngestionQueueUnavailable:
        pass
    write_audit(user_context, "ingestion.run.retry_exhausted", "ingestion_run", run_id, "failed", error, {"retry_count": retry_count, "max_retries": max_retries})
    write_audit(user_context, "ingestion.run.dead_lettered", "ingestion_run", run_id, "failed", error, {"dead_lettered_at": dead_lettered_at})
    return updated


def _heartbeat_safely(worker_id: str, queue_name: str, status: str) -> None:
    try:
        update_worker_heartbeat(worker_id, queue_name, status)
    except IngestionQueueUnavailable:
        # Job state remains durable even if optional heartbeat update is unavailable.
        return
