from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


EventStatus = Literal[
    "new", "ready_for_agent", "running", "waiting_human",
    "completed", "failed", "rejected", "archived",
]


class EventCreateFromRunRequest(BaseModel):
    run_id: str = Field(..., min_length=1)
    cluster_id: str = Field(..., min_length=1)
    title: str | None = Field(default=None, min_length=1)
    event_summary: str | None = Field(default=None, min_length=1)

    model_config = ConfigDict(extra="forbid")


class EventPatchRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    status: EventStatus | None = None
    event_summary: str | None = Field(default=None, min_length=1)

    model_config = ConfigDict(extra="forbid")


class CrisisEventListItem(BaseModel):
    event_id: str
    title: str
    company: str
    risk_level: str
    fact_status: str
    event_status: str
    human_review_required: bool
    source_count: int
    status: EventStatus
    created_at: str
    updated_at: str


class CrisisEventListResponse(BaseModel):
    events: list[CrisisEventListItem]
    count: int


class CrisisEventResponse(BaseModel):
    event_id: str
    cluster_id: str
    source_run_id: str
    title: str
    event_summary: str
    company: str
    risk_level: str
    public_emotion: str
    fact_status: str
    event_status: str
    human_review_required: bool
    source_count: int
    source_items: list[str]
    first_published_at: str
    last_published_at: str
    event_fingerprint: str
    status: EventStatus
    created_at: str
    updated_at: str


class EventCreateResponse(CrisisEventResponse):
    created: bool = True


class EventRunRequest(BaseModel):
    mode: Literal["mock", "llm"] = "mock"
    runtime_mode: Literal["sync"] = "sync"
    force_rerun: bool = False

    model_config = ConfigDict(extra="forbid")


class EventRunResponse(BaseModel):
    event_id: str
    agent_run_id: str
    session_id: str
    status: str
    final_statement_preview: str
    scores: dict[str, Any]
    human_review_required: bool
    policy_triggers: list[str]
    trace_count: int
    automatic_publish: bool = False


class EventReviewResponse(BaseModel):
    event_id: str
    session_id: str
    status: str
    human_review_required: bool
    approval_status: str | None
    policy_triggers: list[str]
    review_reason: str
    allowed_actions: list[str]
