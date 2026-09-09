from __future__ import annotations

from pydantic import BaseModel, Field


class AlertResponse(BaseModel):
    alert_id: str
    entity_id: str
    entity_name: str
    severity: str
    title: str
    reason: str
    related_item_ids: list[str] = Field(default_factory=list)
    related_event_id: str | None = None
    status: str
    created_at: str
    acknowledged_by: str | None = None
    acknowledged_at: str | None = None


class AlertListResponse(BaseModel):
    alerts: list[AlertResponse]
    count: int
