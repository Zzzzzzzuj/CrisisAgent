from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.ingestion.source_registry import ALLOWED_SOURCE_TYPES


class _SourceFields(BaseModel):
    source_name: str = Field(..., min_length=1)
    company_keywords: list[str] = Field(default_factory=list)
    risk_keywords: list[str] = Field(default_factory=list)
    respect_robots: bool = True
    rate_limit_seconds: float = Field(default=3.0, ge=0)
    timeout_seconds: float = Field(default=10.0, gt=0)
    max_items: int = Field(default=5, gt=0)
    query: str | None = Field(default=None, max_length=300)
    language: str | None = Field(default=None, max_length=16)
    lookback_minutes: int = Field(default=60, ge=1, le=10_080)
    domains: list[str] = Field(default_factory=list)
    from_minutes: int | None = Field(default=None, ge=1, le=10_080)
    sort_by: str | None = None
    api_key_env: str | None = Field(default=None, max_length=80)

    @field_validator("company_keywords", "risk_keywords")
    @classmethod
    def keywords_are_strings(cls, values):
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError("keywords must be non-empty strings")
        return [value.strip() for value in values]

    model_config = ConfigDict(extra="forbid")


class SourceCreateRequest(_SourceFields):
    source_id: str = Field(..., min_length=1)
    source_type: str
    url: str = Field(..., min_length=1)
    enabled: bool = False

    @field_validator("source_type")
    @classmethod
    def source_type_is_supported(cls, value):
        if value not in ALLOWED_SOURCE_TYPES:
            raise ValueError("source_type must be rss or article_url")
        return value

    @field_validator("url")
    @classmethod
    def url_is_https(cls, value):
        if not value.lower().startswith("https://"):
            raise ValueError("url must use HTTPS")
        return value

    @model_validator(mode="after")
    def validate_live_news_fields(self):
        if self.source_type in {"gdelt_doc", "news_api"} and not self.query:
            raise ValueError("query is required for gdelt_doc and news_api sources")
        if self.source_type == "news_api" and not self.api_key_env:
            self.api_key_env = "NEWSAPI_KEY"
        if self.sort_by and self.sort_by not in {"relevancy", "publishedAt"}:
            raise ValueError("sort_by must be relevancy or publishedAt")
        return self

class SourceUpdateRequest(BaseModel):
    source_name: str | None = Field(default=None, min_length=1)
    enabled: bool | None = None
    company_keywords: list[str] | None = None
    risk_keywords: list[str] | None = None
    respect_robots: bool | None = None
    rate_limit_seconds: float | None = Field(default=None, ge=0)
    timeout_seconds: float | None = Field(default=None, gt=0)
    max_items: int | None = Field(default=None, gt=0)
    query: str | None = Field(default=None, max_length=300)
    language: str | None = Field(default=None, max_length=16)
    lookback_minutes: int | None = Field(default=None, ge=1, le=10_080)
    domains: list[str] | None = None
    from_minutes: int | None = Field(default=None, ge=1, le=10_080)
    sort_by: str | None = None
    api_key_env: str | None = Field(default=None, max_length=80)

    @field_validator("company_keywords", "risk_keywords")
    @classmethod
    def update_keywords_are_strings(cls, values):
        if values is not None and any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError("keywords must be non-empty strings")
        return [value.strip() for value in values] if values is not None else values

    model_config = ConfigDict(extra="forbid")


class SourceResponse(_SourceFields):
    source_id: str
    source_type: str
    url: str
    enabled: bool
    created_by: str | None = None
    updated_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class SourceListResponse(BaseModel):
    sources: list[SourceResponse]
    count: int


class SourceTestResponse(BaseModel):
    source_id: str
    exists: bool
    enabled: bool
    source_type_supported: bool
    url_https: bool
    keywords_valid: bool
    live_fetch_triggered: bool = False
    test_status: str
    errors: list[str] = Field(default_factory=list)


class SourceFetchPreviewRequest(BaseModel):
    live_fetch: bool = False
    max_items: int | None = Field(default=None, gt=0)

    model_config = ConfigDict(extra="forbid")


class SourceFetchPreviewResponse(BaseModel):
    source_id: str
    source_name: str
    source_type: str
    live_fetch: bool
    status: str
    fetched_count: int = 0
    matched_count: int = 0
    failed_reason: str | None = None
    robots_allowed: bool | None = None
    rate_limit_seconds: float
    timeout_seconds: float
    max_items: int
    items: list[dict] = Field(default_factory=list)
