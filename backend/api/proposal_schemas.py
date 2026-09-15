from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class ProposalCreateRequest(BaseModel):
    diagnosis: dict[str, Any]
    baseline_harness_id: str = Field(..., min_length=1)
    baseline_version: str = Field(..., min_length=1)
    source_run_id: str | None = None
    comparison_id: str | None = None
    replay_case_id: str | None = None
    model_config = ConfigDict(extra="forbid")


class ProposalReviewRequest(BaseModel):
    reason: str = Field(..., min_length=1)
    model_config = ConfigDict(extra="forbid")
