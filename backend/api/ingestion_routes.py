from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.api.ingestion_execution import execute_ingestion_payload, now, validate_ingestion_payload
from backend.api.ingestion_queue import IngestionQueueUnavailable, job_timeout_seconds, reliability_settings, submit_ingestion_job
from backend.api.ingestion_heartbeat import list_worker_heartbeats
from backend.api.ingestion_run_store import get_ingestion_run_store
from backend.api.ingestion_schemas import (
    IngestionRunListResponse,
    IngestionRunRequest,
    IngestionRunResponse,
    IngestionRunSummary,
)
from backend.api.workspace_security import authorize, get_workspace_user, owner_fields, write_audit
from backend.ingestion.source_adapters import RssSourceAdapter

# Compatibility export for existing integrations that reference the historical
# route module. Actual adapter execution lives in ingestion_execution.py.
__all__ = ["router", "RssSourceAdapter"]


router = APIRouter(prefix="/api/ingestion", tags=["ingestion"])


@router.post("/run", response_model=IngestionRunResponse, status_code=status.HTTP_201_CREATED)
def run_ingestion(payload: IngestionRunRequest, user: dict = Depends(get_workspace_user)) -> IngestionRunResponse:
    authorize(user, {"admin", "operator"}, "ingestion.run", "ingestion_run")
    payload_data = payload.model_dump()
    validate_ingestion_payload(payload_data)
    if payload.background and payload.dry_run:
        raise HTTPException(status_code=422, detail="background ingestion does not support dry_run; use background=false for a safe preview.")
    if payload.background:
        return _queue_background_run(payload_data, user)

    result = execute_ingestion_payload(payload_data)
    run = {
        "run_id": str(uuid4()),
        **result,
        "execution_mode": "sync",
        "queue_backend": None,
        "job_id": None,
        **owner_fields(user),
    }
    if not payload.dry_run:
        get_ingestion_run_store().save(run)
        write_audit(
            user,
            "ingestion.run.completed",
            "ingestion_run",
            run["run_id"],
            metadata={"execution_mode": "sync", "queue_backend": None, "background": False, "final_status": run["status"]},
        )
    return IngestionRunResponse(**run)


@router.get("/runs", response_model=IngestionRunListResponse)
def list_ingestion_runs(limit: int = Query(default=20, ge=1, le=100), user: dict = Depends(get_workspace_user)) -> IngestionRunListResponse:
    authorize(user, {"admin", "operator", "viewer"}, "ingestion.list", "ingestion_run")
    runs = get_ingestion_run_store().list_runs(limit)
    summaries = [_summary(run) for run in runs]
    return IngestionRunListResponse(runs=summaries, count=len(summaries))


@router.get("/runs/{run_id}", response_model=IngestionRunResponse)
def get_ingestion_run(run_id: str, user: dict = Depends(get_workspace_user)) -> IngestionRunResponse:
    authorize(user, {"admin", "operator", "viewer"}, "ingestion.view", "ingestion_run", run_id)
    run = get_ingestion_run_store().get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Ingestion run '{run_id}' not found.")
    return IngestionRunResponse(**run)


@router.get("/workers")
def list_ingestion_workers(user: dict = Depends(get_workspace_user)) -> dict:
    authorize(user, {"admin", "operator", "viewer"}, "ingestion.workers", "ingestion_worker")
    try:
        return {"workers": list_worker_heartbeats()}
    except IngestionQueueUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _queue_background_run(payload: dict[str, Any], user: dict) -> IngestionRunResponse:
    store = get_ingestion_run_store()
    max_retries, _, _ = reliability_settings()
    timeout_seconds = job_timeout_seconds()
    run = {
        "run_id": str(uuid4()),
        "status": "queued",
        "live_fetch": bool(payload.get("live_fetch", False)),
        "started_at": None,
        "finished_at": None,
        "source_results": [],
        "raw_count": 0,
        "deduped_count": 0,
        "cluster_count": 0,
        "clusters": [],
        "automatic_publish": False,
        "dry_run": False,
        "execution_mode": "background",
        "queue_backend": "redis",
        "job_id": None,
        "error": None,
        "retry_count": 0,
        "max_retries": max_retries,
        "last_error": None,
        "last_attempt_at": None,
        "next_retry_at": None,
        "dead_lettered_at": None,
        "worker_id": None,
        "heartbeat_at": None,
        "timeout_seconds": timeout_seconds,
        "recovery_reason": None,
        **owner_fields(user),
    }
    store.save(run)
    try:
        job_id = submit_ingestion_job(run["run_id"], _queue_payload(payload), _worker_user_context(user))
    except IngestionQueueUnavailable as exc:
        store.update(run["run_id"], {"status": "failed", "finished_at": now(), "error": str(exc)})
        write_audit(
            user,
            "ingestion.run.failed",
            "ingestion_run",
            run["run_id"],
            "failed",
            str(exc),
            {"execution_mode": "background", "queue_backend": "redis", "background": True, "final_status": "failed"},
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    updated = store.update(run["run_id"], {"job_id": job_id})
    write_audit(
        user,
        "ingestion.run.queued",
        "ingestion_run",
        run["run_id"],
        metadata={"execution_mode": "background", "queue_backend": "redis", "background": True, "job_id": job_id, "final_status": "queued"},
    )
    return IngestionRunResponse(**updated)


def _queue_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_ids": payload.get("source_ids"),
        "live_fetch": bool(payload.get("live_fetch", False)),
        "max_items_override": payload.get("max_items_override"),
        "dry_run": False,
    }


def _worker_user_context(user: dict) -> dict[str, str]:
    return {"id": str(user.get("id", "demo-system")), "username": str(user.get("username", "demo-system")), "role": str(user.get("role", "admin"))}


def _summary(run: dict[str, Any]) -> IngestionRunSummary:
    source_results = run.get("source_results", [])
    return IngestionRunSummary(
        run_id=run["run_id"],
        status=run["status"],
        live_fetch=run["live_fetch"],
        started_at=run.get("started_at"),
        finished_at=run.get("finished_at"),
        execution_mode=run.get("execution_mode", "sync"),
        queue_backend=run.get("queue_backend"),
        job_id=run.get("job_id"),
        error=run.get("error"),
        source_count=len(source_results),
        raw_count=run.get("raw_count", 0),
        deduped_count=run.get("deduped_count", 0),
        cluster_count=run.get("cluster_count", 0),
        failed_source_count=sum(1 for item in source_results if item.get("status") in {"failed", "skipped_by_robots"}),
    )
