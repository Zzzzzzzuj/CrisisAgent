from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


ENTITY_TYPES = {"company", "brand", "product", "person", "organization"}
PRIORITIES = {"low", "medium", "high"}


class WatchlistCreateRequest(BaseModel):
    entity_name: str = Field(..., min_length=1, max_length=200)
    entity_type: str = "company"
    aliases: list[str] = Field(default_factory=list)
    products: list[str] = Field(default_factory=list)
    company_keywords: list[str] = Field(default_factory=list)
    risk_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    priority: str = "medium"
    enabled: bool = False
    archived: bool = False
    model_config = ConfigDict(extra="forbid")


class WatchlistUpdateRequest(BaseModel):
    entity_name: str | None = Field(default=None, min_length=1, max_length=200)
    aliases: list[str] | None = None
    products: list[str] | None = None
    company_keywords: list[str] | None = None
    risk_keywords: list[str] | None = None
    exclude_keywords: list[str] | None = None
    languages: list[str] | None = None
    regions: list[str] | None = None
    priority: str | None = None
    enabled: bool | None = None
    model_config = ConfigDict(extra="forbid")


class WatchlistResponse(BaseModel):
    entity_id: str
    entity_name: str
    entity_type: str
    aliases: list[str]
    products: list[str]
    company_keywords: list[str]
    risk_keywords: list[str]
    exclude_keywords: list[str]
    languages: list[str]
    regions: list[str]
    priority: str
    enabled: bool
    archived: bool = False
    created_by: str | None = None
    owner_id: str | None = None
    created_at: str
    updated_at: str


class WatchlistListResponse(BaseModel):
    watchlists: list[WatchlistResponse]
    count: int
