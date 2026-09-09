from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.api.ingestion_execution import now
from backend.api.ingestion_queue import IngestionQueueUnavailable, submit_ingestion_job
from backend.api.ingestion_run_store import get_ingestion_run_store
from backend.api.workspace_security import write_audit


def recover_stuck_runs(max_age_seconds: int, mode: str = "mark-failed", dry_run: bool = True) -> list[str]:
    if mode not in {"mark-failed", "requeue"}:
        raise ValueError("mode must be mark-failed or requeue")
    store = get_ingestion_run_store()
    affected: list[str] = []
    for run in store.list_runs(limit=100_000):
        if run.get("status") not in {"queued", "running"} or not _is_stale(run, max_age_seconds):
            continue
        run_id = str(run["run_id"])
        affected.append(run_id)
        if dry_run:
            continue
        actor = {"id": run.get("created_by", "recovery"), "role": "admin"}
        if mode == "mark-failed":
            store.update(run_id, {"status": "failed", "finished_at": now(), "last_error": "stuck run recovery", "error": "stuck run recovery", "recovery_reason": "stuck_mark_failed"})
        else:
            payload = {"source_ids": None, "live_fetch": bool(run.get("live_fetch", False)), "max_items_override": None, "dry_run": False}
            job_id = submit_ingestion_job(run_id, payload, actor)
            store.update(run_id, {"status": "queued", "job_id": job_id, "recovery_reason": "stuck_requeued", "next_retry_at": now()})
        write_audit(actor, "ingestion.run.recovered", "ingestion_run", run_id, metadata={"mode": mode, "dry_run": False})
    return affected


def _is_stale(run: dict[str, Any], max_age_seconds: int) -> bool:
    candidate = run.get("heartbeat_at") or run.get("last_attempt_at") or run.get("started_at")
    if not candidate:
        return True
    try:
        timestamp = datetime.fromisoformat(str(candidate).replace("Z", "+00:00"))
    except ValueError:
        return True
    return (datetime.now(timezone.utc) - timestamp).total_seconds() > max_age_seconds
