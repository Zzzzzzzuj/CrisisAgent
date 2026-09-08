from __future__ import annotations

from pydantic import BaseModel


class CrisisUrgencyItem(BaseModel):
    event_id: str
    title: str
    company: str
    risk_level: str
    fact_status: str
    event_status: str
    human_review_required: bool
    source_count: int
    status: str
    urgency_score: int
    severity: str
    priority_reasons: list[str]
    recommended_action: str


class DashboardOverviewResponse(BaseModel):
    total_events: int
    sev1_count: int
    sev2_count: int
    sev3_count: int
    sev4_count: int
    waiting_human_count: int
    unverified_count: int
    conflicting_count: int
    high_risk_count: int
    active_event_count: int
    top_urgent_events: list[CrisisUrgencyItem]
    automatic_publish: bool = False


class SeverityGroup(BaseModel):
    severity: str
    events: list[CrisisUrgencyItem]


class DashboardSeverityResponse(BaseModel):
    groups: list[SeverityGroup]


class DashboardTrendBucket(BaseModel):
    bucket: str
    total: int
    high_risk: int
    waiting_human: int


class DashboardTrendsResponse(BaseModel):
    buckets: list[DashboardTrendBucket]


class SourceHealthItem(BaseModel):
    source_id: str
    latest_status: str
    total_runs: int
    collected_count: int
    no_match_count: int
    failed_count: int
    skipped_by_robots_count: int
    disabled_count: int
    failure_rate: float


class DashboardSourceHealthResponse(BaseModel):
    sources: list[SourceHealthItem]
    count: int


class DashboardReviewQueueResponse(BaseModel):
    events: list[CrisisUrgencyItem]
    count: int
