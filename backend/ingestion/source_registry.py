import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


ALLOWED_SOURCE_TYPES = {"rss", "article_url"}


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
    created_by: str | None = None
    updated_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    def matches(self, text: str) -> bool:
        haystack = str(text or "").lower()
        keywords = self.company_keywords + self.risk_keywords
        return any(keyword.lower() in haystack for keyword in keywords if keyword)


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

    def get(self, source_id: str) -> SourceDefinition:
        try:
            return self._sources[source_id]
        except KeyError as exc:
            raise KeyError(f"Source is not allowlisted: {source_id}") from exc

    def enabled_sources(self) -> list[SourceDefinition]:
        return [source for source in self._sources.values() if source.enabled]

    def all_sources(self) -> list[SourceDefinition]:
        return list(self._sources.values())
