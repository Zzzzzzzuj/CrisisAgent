from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.ingestion.source_registry import ALLOWED_SOURCE_TYPES


class _SourceFields(BaseModel):
    source_name: str = Field(..., min_length=1)
    company_keywords: list[str] = Field(default_factory=list)
    risk_keywords: list[str] = Field(default_factory=list)
    respect_robots: bool = True
    rate_limit_seconds: float = Field(default=3.0, ge=0)
    timeout_seconds: float = Field(default=10.0, gt=0)
    max_items: int = Field(default=5, gt=0)

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

class SourceUpdateRequest(BaseModel):
    source_name: str | None = Field(default=None, min_length=1)
    enabled: bool | None = None
    company_keywords: list[str] | None = None
    risk_keywords: list[str] | None = None
    respect_robots: bool | None = None
    rate_limit_seconds: float | None = Field(default=None, ge=0)
    timeout_seconds: float | None = Field(default=None, gt=0)
    max_items: int | None = Field(default=None, gt=0)

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
