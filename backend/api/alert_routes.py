from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.alert_schemas import AlertListResponse, AlertResponse
from backend.api.alert_store import get_alert_store
from backend.api.workspace_security import authorize, get_workspace_user, write_audit

router = APIRouter(prefix="/api/alerts", tags=["alerts"])
READ = {"admin", "operator", "legal_reviewer", "viewer"}


@router.get("", response_model=AlertListResponse)
def list_alerts(status: str | None = None, limit: int = Query(100, ge=1, le=200), user: dict = Depends(get_workspace_user)):
    authorize(user, READ, "alert.list", "alert")
    values = get_alert_store().list(status, limit)
    return AlertListResponse(alerts=[AlertResponse(**item) for item in values], count=len(values))


@router.post("/{alert_id}/ack", response_model=AlertResponse)
def acknowledge_alert(alert_id: str, user: dict = Depends(get_workspace_user)):
    authorize(user, {"admin", "operator", "legal_reviewer"}, "alert.ack", "alert", alert_id)
    try:
        value = get_alert_store().ack(alert_id, str(user.get("id", "demo-system")))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Alert '{exc.args[0]}' not found.") from exc
    write_audit(user, "alert.ack", "alert", alert_id)
    return AlertResponse(**value)
