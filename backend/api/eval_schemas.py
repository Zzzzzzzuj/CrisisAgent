from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


EvalDimension = Literal["ingestion", "event", "urgency", "agent_run", "report", "tool", "golden_case"]


class EvalRunRequest(BaseModel):
    dimensions: list[EvalDimension] | None = None
    dry_run: bool = False

    model_config = ConfigDict(extra="forbid")


class EvalItem(BaseModel):
    case_id: str
    dimension: EvalDimension
    name: str
    passed: bool
    score: float
    expected: Any
    actual: Any
    reason: str
    related_event_id: str | None = None
    related_run_id: str | None = None


class EvalRunResponse(BaseModel):
    eval_run_id: str
    created_at: str
    finished_at: str
    status: Literal["completed", "failed"]
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float
    dimensions: dict[str, dict[str, Any]]
    items: list[EvalItem]
    failed_items: list[EvalItem]
    summary: dict[str, Any]
    automatic_publish: bool = False
    dry_run: bool = False
    created_by: str | None = None


class EvalRunListItem(BaseModel):
    eval_run_id: str
    created_at: str
    finished_at: str
    status: Literal["completed", "failed"]
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float
    dimensions: dict[str, dict[str, Any]]
    automatic_publish: bool = False


class EvalRunListResponse(BaseModel):
    runs: list[EvalRunListItem]
    count: int


class EvalOverviewResponse(BaseModel):
    latest_eval_run_id: str | None
    latest_pass_rate: float | None
    total_runs: int
    total_cases: int
    passed_cases: int
    failed_cases: int
    dimensions_summary: dict[str, dict[str, Any]]
    top_failed_dimensions: list[str]
    automatic_publish: bool = False


class EvalRegressionResponse(BaseModel):
    not_enough_runs: bool
    current_eval_run_id: str | None = None
    previous_eval_run_id: str | None = None
    current_pass_rate: float | None = None
    previous_pass_rate: float | None = None
    delta: float | None = None
    newly_failed_cases: list[str] = Field(default_factory=list)
    recovered_cases: list[str] = Field(default_factory=list)
