from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ToolDefinitionResponse(BaseModel):
    tool_name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    risk_level: str
    read_only: bool
    requires_human_confirmation: bool
    version: str


class ToolListResponse(BaseModel):
    tools: list[ToolDefinitionResponse]
    count: int


class ToolRunRequest(BaseModel):
    tool_name: str = Field(..., min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = Field(default=None, max_length=200)
    session_id: str | None = Field(default=None, max_length=200)
    dry_run: bool = False

    model_config = ConfigDict(extra="forbid")


class ToolRunResponse(BaseModel):
    tool_run_id: str
    tool_name: str
    status: Literal["success", "failed", "denied"]
    output: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    human_review_required: bool = False
    trace: dict[str, Any] = Field(default_factory=dict)
    started_at: str
    finished_at: str
    request_id: str | None = None
    session_id: str | None = None
    dry_run: bool = False
