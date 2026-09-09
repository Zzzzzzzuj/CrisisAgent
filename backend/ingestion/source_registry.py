import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


ALLOWED_SOURCE_TYPES = {"rss", "article_url", "gdelt_doc", "news_api"}


@dataclass(frozen=True)
class SourceDefinition:
    source_id: str
    source_name: str
    source_type: str
    url: str
    enabled: bool = False
    company_keywords: tuple[str, ...] = ()
    risk_keywords: tuple[str, ...] = ()
    respect_robots: bool = True
    rate_limit_seconds: float = 3.0
    timeout_seconds: float = 10.0
    max_items: int = 5
    query: str | None = None
    language: str | None = None
    lookback_minutes: int = 60
    domains: tuple[str, ...] = ()
    from_minutes: int | None = None
    sort_by: str | None = None
    api_key_env: str | None = None
    created_by: str | None = None
    updated_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    def matches(self, text: str) -> bool:
        haystack = str(text or "").lower()
        keywords = self.company_keywords + self.risk_keywords
        return any(keyword.lower() in haystack for keyword in keywords if keyword)

    def matched_keywords(self, text: str) -> tuple[list[str], list[str]]:
        haystack = str(text or "").lower()
        return (
            [keyword for keyword in self.company_keywords if keyword.lower() in haystack],
            [keyword for keyword in self.risk_keywords if keyword.lower() in haystack],
        )


class SourceRegistry:
    def __init__(self, sources: list[SourceDefinition]):
        self._sources = {source.source_id: source for source in sources}

    @classmethod
    def from_file(cls, path: str | Path) -> "SourceRegistry":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("sources"), list):
            raise ValueError("Source registry must contain a sources array.")

        sources = []
        for raw in payload["sources"]:
            if not isinstance(raw, dict):
                raise ValueError("Each source registry entry must be an object.")
            source = SourceDefinition(
                source_id=str(raw.get("source_id", "")).strip(),
                source_name=str(raw.get("source_name", "")).strip(),
                source_type=str(raw.get("source_type", "")).strip(),
                url=str(raw.get("url", "")).strip(),
                enabled=raw.get("enabled", False) is True,
                company_keywords=tuple(str(value) for value in raw.get("company_keywords", []) or []),
                risk_keywords=tuple(str(value) for value in raw.get("risk_keywords", []) or []),
                respect_robots=raw.get("respect_robots", True) is not False,
                rate_limit_seconds=float(raw.get("rate_limit_seconds", 3)),
                timeout_seconds=float(raw.get("timeout_seconds", 10)),
                max_items=int(raw.get("max_items", 5)),
                query=raw.get("query"), language=raw.get("language"),
                lookback_minutes=int(raw.get("lookback_minutes", 60)),
                domains=tuple(str(value) for value in raw.get("domains", []) or []),
                from_minutes=raw.get("from_minutes"), sort_by=raw.get("sort_by"),
                api_key_env=raw.get("api_key_env"),
                created_by=raw.get("created_by"), updated_by=raw.get("updated_by"),
                created_at=raw.get("created_at"), updated_at=raw.get("updated_at"),
            )
            cls._validate(source)
            if source.source_id in {item.source_id for item in sources}:
                raise ValueError(f"Duplicate source_id: {source.source_id}")
            sources.append(source)
        return cls(sources)

    @staticmethod
    def _validate(source: SourceDefinition) -> None:
        if not source.source_id or not source.source_name or not source.url:
            raise ValueError("source_id, source_name and url are required.")
        if source.source_type not in ALLOWED_SOURCE_TYPES:
            raise ValueError(f"Unsupported source_type: {source.source_type}")
        parsed = urlparse(source.url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("Live source URLs must use https and include a host.")
        if source.rate_limit_seconds < 0 or source.timeout_seconds <= 0 or source.max_items <= 0:
            raise ValueError("Source limits must be positive and rate_limit_seconds cannot be negative.")
        if source.source_type in {"gdelt_doc", "news_api"}:
            if not source.query or len(source.query.strip()) > 300:
                raise ValueError("News API sources require a query up to 300 characters.")
        if source.lookback_minutes <= 0 or source.lookback_minutes > 10_080:
            raise ValueError("lookback_minutes must be between 1 and 10080.")
        if source.from_minutes is not None and (source.from_minutes <= 0 or source.from_minutes > 10_080):
            raise ValueError("from_minutes must be between 1 and 10080.")
        if source.sort_by and source.sort_by not in {"relevancy", "publishedAt"}:
            raise ValueError("sort_by must be relevancy or publishedAt.")

    def get(self, source_id: str) -> SourceDefinition:
        try:
            return self._sources[source_id]
        except KeyError as exc:
            raise KeyError(f"Source is not allowlisted: {source_id}") from exc

    def enabled_sources(self) -> list[SourceDefinition]:
        return [source for source in self._sources.values() if source.enabled]

    def all_sources(self) -> list[SourceDefinition]:
        return list(self._sources.values())
