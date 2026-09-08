from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.product_storage.factory import get_audit_log_repository
from backend.api.workspace_security import authorize, get_workspace_user

router = APIRouter(prefix="/api/audit", tags=["audit"])

@router.get("/logs")
def list_audit_logs(limit: int = Query(50, ge=1, le=200), action: str | None = None, actor_id: str | None = None, resource_type: str | None = None, user: dict = Depends(get_workspace_user)) -> dict:
    authorize(user, {"admin"}, "audit.view", "audit_log")
    logs = get_audit_log_repository().list_logs(limit=limit, action=action, actor_id=actor_id, resource_type=resource_type)
    return {"logs": logs, "count": len(logs)}
