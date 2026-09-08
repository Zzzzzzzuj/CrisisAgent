from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IngestionRunRequest(BaseModel):
    source_ids: list[str] | None = None
    live_fetch: bool = False
    max_items_override: int | None = Field(default=None, gt=0)
    dry_run: bool = False

    model_config = ConfigDict(extra="forbid")


class IngestionRunSummary(BaseModel):
    run_id: str
    status: str
    live_fetch: bool
    started_at: str
    finished_at: str
    source_count: int
    raw_count: int
    deduped_count: int
    cluster_count: int
    failed_source_count: int


class IngestionRunListResponse(BaseModel):
    runs: list[IngestionRunSummary]
    count: int


class IngestionRunResponse(BaseModel):
    run_id: str
    status: str
    live_fetch: bool
    started_at: str
    finished_at: str
    source_results: list[dict[str, Any]]
    raw_count: int
    deduped_count: int
    cluster_count: int
    clusters: list[dict[str, Any]]
    automatic_publish: bool
    dry_run: bool
    created_by: str | None = None
    owner_id: str | None = None
