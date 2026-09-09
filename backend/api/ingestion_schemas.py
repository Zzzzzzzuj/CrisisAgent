from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IngestionRunRequest(BaseModel):
    source_ids: list[str] | None = None
    live_fetch: bool = False
    max_items_override: int | None = Field(default=None, gt=0)
    dry_run: bool = False
    background: bool = False

    model_config = ConfigDict(extra="forbid")


class IngestionRunSummary(BaseModel):
    run_id: str
    status: str
    live_fetch: bool
    started_at: str | None = None
    finished_at: str | None = None
    execution_mode: str = "sync"
    queue_backend: str | None = None
    job_id: str | None = None
    error: str | None = None
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
    started_at: str | None = None
    finished_at: str | None = None
    source_results: list[dict[str, Any]] = Field(default_factory=list)
    raw_count: int = 0
    deduped_count: int = 0
    cluster_count: int = 0
    clusters: list[dict[str, Any]] = Field(default_factory=list)
    automatic_publish: bool = False
    dry_run: bool = False
    execution_mode: str = "sync"
    queue_backend: str | None = None
    job_id: str | None = None
    error: str | None = None
    retry_count: int | None = None
    max_retries: int | None = None
    last_error: str | None = None
    last_attempt_at: str | None = None
    next_retry_at: str | None = None
    dead_lettered_at: str | None = None
    worker_id: str | None = None
    heartbeat_at: str | None = None
    timeout_seconds: int | None = None
    recovery_reason: str | None = None
    created_by: str | None = None
    owner_id: str | None = None
