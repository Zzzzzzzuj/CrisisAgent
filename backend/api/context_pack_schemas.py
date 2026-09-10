from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ContextPackBuildRequest(BaseModel):
    event_id: str | None = None
    event_text: str | None = None
    entity_id: str | None = None
    include_memories: bool = True
    token_budget_hint: int = Field(default=3000, gt=0, le=20_000)
    target_agent: str | None = Field(default=None, pattern="^(sentiment|writer|redteam|legal|writer_v2|decision)$")
    compression_mode: str = Field(default="auto", pattern="^(auto|off)$")

    model_config = ConfigDict(extra="forbid")


class ContextPackBuildResponse(BaseModel):
    context_pack: dict[str, Any]
    memory_count: int
    dropped_fields: list[dict[str, Any]]
    safety_notes: list[str]
    agent_specific_focus: dict[str, Any] = Field(default_factory=dict)
    selected_case_ids: list[str] = Field(default_factory=list)
    latest_round_summary: dict[str, Any] | None = None
    compression_level: str = "green"
    usage_ratio: float = 0.0
    estimated_chars: int = 0
    token_budget_hint: int = 3000
    compression_actions: list[str] = Field(default_factory=list)
    aggregate_summary: str | None = None
    preserved_fields: list[str] = Field(default_factory=list)
