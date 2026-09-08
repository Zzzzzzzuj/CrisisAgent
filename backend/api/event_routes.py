from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from backend.api.event_schemas import (
    CrisisEventListItem,
    CrisisEventListResponse,
    CrisisEventResponse,
    EventCreateFromRunRequest,
    EventCreateResponse,
    EventPatchRequest,
)
from backend.api.event_store import ALLOWED_EVENT_STATUSES, get_crisis_event_store
from backend.api.ingestion_run_store import get_ingestion_run_store


router = APIRouter(prefix="/api/events", tags=["events"])


@router.post("/from-ingestion-run", response_model=EventCreateResponse, status_code=status.HTTP_201_CREATED)
def create_event_from_ingestion_run(payload: EventCreateFromRunRequest) -> EventCreateResponse:
    run = get_ingestion_run_store().get(payload.run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Ingestion run '{payload.run_id}' not found.")

    cluster = next(
        (item for item in run.get("clusters", []) if item.get("cluster_id") == payload.cluster_id),
        None,
    )
    if cluster is None:
        raise HTTPException(
            status_code=404,
            detail=f"Cluster '{payload.cluster_id}' not found in ingestion run '{payload.run_id}'.",
        )

    event, created = get_crisis_event_store().create_from_cluster(
        source_run_id=payload.run_id,
        cluster=cluster,
        title=payload.title,
        event_summary=payload.event_summary,
    )
    return EventCreateResponse(**event, created=created)


@router.get("", response_model=CrisisEventListResponse)
def list_events(
    status_filter: str | None = Query(default=None, alias="status"),
    risk_level: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> CrisisEventListResponse:
    events = get_crisis_event_store().list_events(
        status=status_filter,
        risk_level=risk_level,
        limit=limit,
    )
    items = [CrisisEventListItem(**_list_fields(event)) for event in events]
    return CrisisEventListResponse(events=items, count=len(items))


@router.get("/{event_id}", response_model=CrisisEventResponse)
def get_event(event_id: str) -> CrisisEventResponse:
    event = get_crisis_event_store().get(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"Crisis event '{event_id}' not found.")
    return CrisisEventResponse(**event)


@router.patch("/{event_id}", response_model=CrisisEventResponse)
def update_event(event_id: str, payload: EventPatchRequest) -> CrisisEventResponse:
    changes = payload.model_dump(exclude_unset=True)
    if "status" in changes and changes["status"] not in ALLOWED_EVENT_STATUSES:
        raise HTTPException(status_code=422, detail=f"Unsupported event status: {changes['status']}")
    event = get_crisis_event_store().update(event_id, changes)
    if event is None:
        raise HTTPException(status_code=404, detail=f"Crisis event '{event_id}' not found.")
    return CrisisEventResponse(**event)


@router.post("/{event_id}/archive", response_model=CrisisEventResponse)
def archive_event(event_id: str) -> CrisisEventResponse:
    event = get_crisis_event_store().archive(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"Crisis event '{event_id}' not found.")
    return CrisisEventResponse(**event)


def _list_fields(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": event["event_id"],
        "title": event["title"],
        "company": event["company"],
        "risk_level": event["risk_level"],
        "fact_status": event["fact_status"],
        "event_status": event["event_status"],
        "human_review_required": event["human_review_required"],
        "source_count": event["source_count"],
        "status": event["status"],
        "created_at": event["created_at"],
        "updated_at": event["updated_at"],
    }
