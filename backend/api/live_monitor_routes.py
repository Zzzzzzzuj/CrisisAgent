from __future__ import annotations

import os
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.api.ingestion_execution import api_live_fetch_enabled, now
from backend.api.ingestion_queue import IngestionQueueUnavailable, submit_live_monitor_job
from backend.api.live_monitor_execution import execute_monitor_payload
from backend.api.live_monitor_schemas import LiveMonitorRunListResponse, LiveMonitorRunRequest, LiveMonitorRunResponse
from backend.api.live_monitor_store import get_live_monitor_run_store
from backend.api.watchlist_store import get_watchlist_store
from backend.api.workspace_security import authorize, get_workspace_user, owner_fields, write_audit

router = APIRouter(prefix="/api/live-monitor", tags=["live-monitor"])


@router.post("/run", response_model=LiveMonitorRunResponse, status_code=status.HTTP_201_CREATED)
def run_live_monitor(payload: LiveMonitorRunRequest, user: dict = Depends(get_workspace_user)):
    authorize(user, {"admin", "operator"}, "live_monitor.run", "monitor_run")
    if payload.live_fetch and not api_live_fetch_enabled():
        raise HTTPException(status_code=403, detail="live fetch is disabled by server config; set ENABLE_API_LIVE_FETCH=true to enable it.")
    entities = get_watchlist_store().list(enabled=True)
    if payload.entity_ids is not None:
        missing = set(payload.entity_ids) - {item["entity_id"] for item in entities}
        if missing:
            raise HTTPException(status_code=404, detail=f"Enabled watchlist not found: {sorted(missing)[0]}")
        entities = [item for item in entities if item["entity_id"] in set(payload.entity_ids)]
    if not entities:
        raise HTTPException(status_code=400, detail="No enabled watchlist entities selected.")
    run_id = str(uuid4())
    run = {"monitor_run_id": run_id, "status": "queued" if payload.background else "running", "live_fetch": payload.live_fetch, "background": payload.background, "entity_count": len(entities), "provider_count": len(payload.providers or ["gdelt_doc", "news_api", "rss"]), "source_results": [], "item_count": 0, "cluster_count": 0, "alert_count": 0, "automatic_publish": False, "error": None, **owner_fields(user)}
    store = get_live_monitor_run_store()
    if payload.background:
        store.save(run)
        try:
            job_id = submit_live_monitor_job(run_id, payload.model_dump(), {"id": user.get("id", "demo-system"), "role": user.get("role", "admin")})
        except IngestionQueueUnavailable as exc:
            store.update(run_id, {"status": "failed", "error": str(exc)})
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        run = store.update(run_id, {"job_id": job_id})
    else:
        run = store.save(execute_monitor_payload(payload.model_dump(), run_id))
    write_audit(user, "live_monitor.run", "monitor_run", run_id, metadata={"live_fetch": payload.live_fetch, "background": payload.background})
    return LiveMonitorRunResponse(**run)


@router.get("/runs", response_model=LiveMonitorRunListResponse)
def list_monitor_runs(limit: int = Query(20, ge=1, le=100), user: dict = Depends(get_workspace_user)):
    authorize(user, {"admin", "operator", "legal_reviewer", "viewer"}, "live_monitor.list", "monitor_run")
    values = get_live_monitor_run_store().list(limit)
    return LiveMonitorRunListResponse(runs=[LiveMonitorRunResponse(**item) for item in values], count=len(values))


@router.get("/runs/{monitor_run_id}", response_model=LiveMonitorRunResponse)
def get_monitor_run(monitor_run_id: str, user: dict = Depends(get_workspace_user)):
    authorize(user, {"admin", "operator", "legal_reviewer", "viewer"}, "live_monitor.view", "monitor_run", monitor_run_id)
    value = get_live_monitor_run_store().get(monitor_run_id)
    if value is None:
        raise HTTPException(status_code=404, detail=f"Monitor run '{monitor_run_id}' not found.")
    return LiveMonitorRunResponse(**value)
