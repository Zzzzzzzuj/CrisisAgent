from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HarnessComparisonCreateRequest(BaseModel):
    baseline_harness_id: str = Field(..., min_length=1)
    baseline_version: str = Field(..., min_length=1)
    candidate_harness_id: str = Field(..., min_length=1)
    candidate_version: str = Field(..., min_length=1)
    mode: str = "golden"
    replay_case_ids: list[str] | None = None
    mode: str = "golden"
    replay_case_ids: list[str] | None = None
    model_config = ConfigDict(extra="forbid")


class HarnessComparisonListResponse(BaseModel):
    comparisons: list[dict[str, Any]]
    count: int
