from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.collected_item_schemas import CollectedItemListResponse, CollectedItemResponse
from backend.api.collected_item_store import get_collected_item_store
from backend.api.workspace_security import authorize, get_workspace_user


router = APIRouter(prefix="/api/collected-items", tags=["collected-items"])
_READ_ROLES = {"admin", "operator", "legal_reviewer", "viewer"}


@router.get("", response_model=CollectedItemListResponse)
def list_collected_items(
    source_id: str | None = None,
    ingestion_run_id: str | None = None,
    status: str | None = None,
    entity_id: str | None = None,
    provider: str | None = None,
    monitor_run_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    user: dict = Depends(get_workspace_user),
) -> CollectedItemListResponse:
    authorize(user, _READ_ROLES, "collected_item.list", "collected_item")
    items = get_collected_item_store().list_items(source_id=source_id, ingestion_run_id=ingestion_run_id, status=status, entity_id=entity_id, provider=provider, monitor_run_id=monitor_run_id, limit=limit)
    return CollectedItemListResponse(items=[CollectedItemResponse(**item) for item in items], count=len(items))


@router.get("/{item_id}", response_model=CollectedItemResponse)
def get_collected_item(item_id: str, user: dict = Depends(get_workspace_user)) -> CollectedItemResponse:
    authorize(user, _READ_ROLES, "collected_item.view", "collected_item", item_id)
    item = get_collected_item_store().get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Collected item '{item_id}' not found.")
    return CollectedItemResponse(**item)
