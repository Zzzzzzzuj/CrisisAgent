from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field, ConfigDict


class LiveMonitorRunRequest(BaseModel):
    entity_ids: list[str] | None = None
    providers: list[str] | None = None
    lookback_minutes: int = Field(default=60, ge=1, le=10080)
    max_items_per_entity: int = Field(default=10, ge=1, le=100)
    background: bool = True
    live_fetch: bool = False
    auto_create_events: bool = False
    model_config = ConfigDict(extra="forbid")


class LiveMonitorRunResponse(BaseModel):
    monitor_run_id: str
    status: str
    live_fetch: bool
    background: bool
    entity_count: int
    provider_count: int
    source_results: list[dict[str, Any]] = Field(default_factory=list)
    clusters: list[dict[str, Any]] = Field(default_factory=list)
    item_count: int = 0
    cluster_count: int = 0
    alert_count: int = 0
    automatic_publish: bool = False
    error: str | None = None
    job_id: str | None = None


class LiveMonitorRunListResponse(BaseModel):
    runs: list[LiveMonitorRunResponse]
    count: int
