from __future__ import annotations

from typing import Any

from backend.api.ingestion_execution import execute_ingestion_payload, now
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

    store.update(run_id, {"status": "running", "started_at": now(), "error": None})
    write_audit(
        user_context,
        "ingestion.run.started",
        "ingestion_run",
        run_id,
        metadata={"execution_mode": "background", "queue_backend": "redis", "background": True},
    )
    try:
        result = execute_ingestion_payload(payload)
        final_status = result["status"]
        updated = store.update(run_id, {**result, "execution_mode": "background", "queue_backend": "redis"})
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
        updated = store.update(
            run_id,
            {"status": "failed", "finished_at": now(), "error": str(exc), "execution_mode": "background", "queue_backend": "redis"},
        )
        write_audit(
            user_context,
            "ingestion.run.failed",
            "ingestion_run",
            run_id,
            "failed",
            str(exc),
            {"execution_mode": "background", "queue_backend": "redis", "background": True, "job_id": updated.get("job_id"), "final_status": "failed"},
        )
        return updated
