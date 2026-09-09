from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.api.case_memory_schemas import (
    CaseMemoryCreateRequest,
    CaseMemoryListResponse,
    CaseMemoryResponse,
    CaseMemoryUpdateRequest,
)
from backend.api.case_memory_store import get_case_memory_store
from backend.api.event_run_store import get_event_agent_run_store
from backend.api.event_store import get_crisis_event_store
from backend.api.workspace_security import authorize, get_workspace_user, write_audit


router = APIRouter(prefix="/api/case-memories", tags=["case-memory"])
READ_ROLES = {"admin", "operator", "legal_reviewer", "viewer"}
WRITE_ROLES = {"admin", "operator"}


@router.get("", response_model=CaseMemoryListResponse)
def list_memories(
    entity_id: str | None = None,
    crisis_type: str | None = None,
    risk_level: str | None = None,
    tag: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(get_workspace_user),
) -> CaseMemoryListResponse:
    authorize(user, READ_ROLES, "case_memory.list", "case_memory")
    values = get_case_memory_store().list_memories(
        entity_id=entity_id, crisis_type=crisis_type, risk_level=risk_level, tag=tag, limit=limit,
    )
    return CaseMemoryListResponse(memories=[CaseMemoryResponse(**item) for item in values], count=len(values))


@router.post("", response_model=CaseMemoryResponse, status_code=status.HTTP_201_CREATED)
def create_memory(payload: CaseMemoryCreateRequest, user: dict = Depends(get_workspace_user)) -> CaseMemoryResponse:
    authorize(user, WRITE_ROLES, "case_memory.create", "case_memory", payload.source_event_id)
    event = get_crisis_event_store().get(payload.source_event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"Crisis event '{payload.source_event_id}' not found.")
    if not _event_is_memory_eligible(event):
        raise HTTPException(
            status_code=409,
            detail="Only completed or approved human-reviewed events can enter Case Memory.",
        )
    values = payload.model_dump()
    if not values.get("entity_id"):
        values["entity_id"] = event.get("entity_id")
    if not values.get("entity_name"):
        values["entity_name"] = event.get("company")
    memory = get_case_memory_store().create(
        values,
        actor_id=str(user.get("id", "demo-system")),
        owner_id=str(user.get("id", "demo-system")),
    )
    write_audit(user, "case_memory.create", "case_memory", memory["memory_id"])
    return CaseMemoryResponse(**memory)


@router.get("/{memory_id}", response_model=CaseMemoryResponse)
def get_memory(memory_id: str, user: dict = Depends(get_workspace_user)) -> CaseMemoryResponse:
    authorize(user, READ_ROLES, "case_memory.view", "case_memory", memory_id)
    value = get_case_memory_store().get(memory_id)
    if value is None:
        raise HTTPException(status_code=404, detail=f"Case memory '{memory_id}' not found.")
    return CaseMemoryResponse(**value)


@router.patch("/{memory_id}", response_model=CaseMemoryResponse)
def update_memory(memory_id: str, payload: CaseMemoryUpdateRequest,
                  user: dict = Depends(get_workspace_user)) -> CaseMemoryResponse:
    authorize(user, WRITE_ROLES, "case_memory.update", "case_memory", memory_id)
    value = get_case_memory_store().update(memory_id, payload.model_dump(exclude_unset=True))
    if value is None:
        raise HTTPException(status_code=404, detail=f"Case memory '{memory_id}' not found.")
    write_audit(user, "case_memory.update", "case_memory", memory_id)
    return CaseMemoryResponse(**value)


@router.post("/{memory_id}/archive", response_model=CaseMemoryResponse)
def archive_memory(memory_id: str, user: dict = Depends(get_workspace_user)) -> CaseMemoryResponse:
    authorize(user, WRITE_ROLES, "case_memory.archive", "case_memory", memory_id)
    value = get_case_memory_store().archive(memory_id)
    if value is None:
        raise HTTPException(status_code=404, detail=f"Case memory '{memory_id}' not found.")
    write_audit(user, "case_memory.archive", "case_memory", memory_id)
    return CaseMemoryResponse(**value)


def _event_is_memory_eligible(event: dict) -> bool:
    run = get_event_agent_run_store().get_latest(str(event.get("event_id", "")))
    approval = run.get("approval") if isinstance(run, dict) else None
    if isinstance(approval, dict) and approval.get("decision") == "approved":
        return True
    if event.get("status") != "completed":
        return False
    return event.get("fact_status") not in {"unverified", "conflicting"} and event.get("event_status") != "uncertain"
