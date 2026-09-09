from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CaseMemoryCreateRequest(BaseModel):
    source_event_id: str = Field(..., min_length=1)
    source_report_id: str | None = None
    entity_id: str | None = None
    entity_name: str | None = None
    crisis_type: str = Field(..., min_length=1)
    risk_level: str = Field(..., min_length=1)
    fact_status: str = Field(..., min_length=1)
    event_status: str = Field(..., min_length=1)
    final_statement_summary: str = Field(..., min_length=1, max_length=1000)
    legal_risk_summary: str = Field(default="", max_length=1000)
    redteam_summary: str = Field(default="", max_length=1000)
    human_review_summary: str = Field(default="", max_length=1000)
    response_strategy: str = Field(default="", max_length=1000)
    tags: list[str] = Field(default_factory=list)
    created_from: str = Field(default="human_review", min_length=1)
    case_group_id: str | None = None
    round_index: int | None = Field(default=None, ge=1)
    previous_memory_id: str | None = None
    previous_statement_summary: str | None = Field(default=None, max_length=1000)
    public_reaction_summary: str | None = Field(default=None, max_length=1000)
    what_changed_since_previous: str | None = Field(default=None, max_length=1000)
    previous_redteam_findings: list[str] | None = None
    unresolved_redteam_findings: list[str] | None = None
    previous_legal_constraints: list[str] | None = None
    avoid_repeating_points: list[str] | None = None
    outcome: str | None = None

    model_config = ConfigDict(extra="forbid")


class CaseMemoryUpdateRequest(BaseModel):
    final_statement_summary: str | None = Field(default=None, min_length=1, max_length=1000)
    legal_risk_summary: str | None = Field(default=None, max_length=1000)
    redteam_summary: str | None = Field(default=None, max_length=1000)
    human_review_summary: str | None = Field(default=None, max_length=1000)
    response_strategy: str | None = Field(default=None, max_length=1000)
    tags: list[str] | None = None
    archived: bool | None = None
    case_group_id: str | None = None
    round_index: int | None = Field(default=None, ge=1)
    previous_memory_id: str | None = None
    previous_statement_summary: str | None = Field(default=None, max_length=1000)
    public_reaction_summary: str | None = Field(default=None, max_length=1000)
    what_changed_since_previous: str | None = Field(default=None, max_length=1000)
    previous_redteam_findings: list[str] | None = None
    unresolved_redteam_findings: list[str] | None = None
    previous_legal_constraints: list[str] | None = None
    avoid_repeating_points: list[str] | None = None
    outcome: str | None = None

    model_config = ConfigDict(extra="forbid")


class CaseMemoryResponse(BaseModel):
    memory_id: str
    source_event_id: str
    source_report_id: str | None = None
    entity_id: str | None = None
    entity_name: str | None = None
    crisis_type: str
    risk_level: str
    fact_status: str
    event_status: str
    final_statement_summary: str
    legal_risk_summary: str
    redteam_summary: str
    human_review_summary: str
    response_strategy: str
    tags: list[str]
    created_from: str
    created_by: str
    owner_id: str
    created_at: str
    updated_at: str
    archived: bool
    case_group_id: str | None = None
    round_index: int | None = None
    previous_memory_id: str | None = None
    previous_statement_summary: str | None = None
    public_reaction_summary: str | None = None
    what_changed_since_previous: str | None = None
    previous_redteam_findings: list[str] | None = None
    unresolved_redteam_findings: list[str] | None = None
    previous_legal_constraints: list[str] | None = None
    avoid_repeating_points: list[str] | None = None
    outcome: str | None = None


class CaseMemoryListResponse(BaseModel):
    memories: list[CaseMemoryResponse]
    count: int
