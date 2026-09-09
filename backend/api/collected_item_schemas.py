from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CollectedItemResponse(BaseModel):
    item_id: str
    source_id: str
    source_name: str
    source_type: str
    ingestion_run_id: str
    title: str
    url: str
    summary: str
    content_preview: str
    published_at: str
    collected_at: str
    matched_company_keywords: list[str] = Field(default_factory=list)
    matched_risk_keywords: list[str] = Field(default_factory=list)
    content_hash: str
    status: str
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    entity_id: str | None = None
    entity_name: str | None = None
    provider: str | None = None
    relevance_score: float | None = None
    risk_score: float | None = None
    sentiment_hint: str | None = None
    monitor_run_id: str | None = None


class CollectedItemListResponse(BaseModel):
    items: list[CollectedItemResponse]
    count: int
