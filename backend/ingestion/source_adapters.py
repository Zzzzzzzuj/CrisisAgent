import csv
import json
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import time
import xml.etree.ElementTree as ET

import httpx

from .article_extractor import extract_article
from .robots import RobotsChecker
from .schemas import RawSentimentItem
from .source_registry import SourceDefinition


REQUIRED_FIELDS = {
    "item_id",
    "source_name",
    "source_url",
    "title",
    "content",
    "published_at",
    "company",
    "fact_status",
}


@dataclass(frozen=True)
class FetchResult:
    source_id: str
    source_name: str
    status: str
    fetched_count: int
    matched_count: int
    failed_reason: str | None
    items: list[RawSentimentItem]


def _to_item(row: dict, index: int) -> RawSentimentItem:
    values = {key: str(row.get(key, "") or "").strip() for key in REQUIRED_FIELDS}
    return RawSentimentItem(
        item_id=values["item_id"] or f"item_{index}",
        source_name=values["source_name"] or "unknown",
        source_url=values["source_url"],
        title=values["title"],
        content=values["content"],
        published_at=values["published_at"],
        company=values["company"] or "unknown",
        fact_status=values["fact_status"] or "unverified",
    )


class LocalJsonSourceAdapter:
    def load(self, path: str | Path) -> list[RawSentimentItem]:
        rows = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise ValueError("Local sentiment JSON must contain an array.")
        return [_to_item(row if isinstance(row, dict) else {}, index) for index, row in enumerate(rows, 1)]


class LocalCsvSourceAdapter:
    def load(self, path: str | Path) -> list[RawSentimentItem]:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
            return [_to_item(row, index) for index, row in enumerate(csv.DictReader(handle), 1)]


class _RateLimitedAdapter:
    _last_fetch_at: dict[str, float] = {}

    @classmethod
    def _wait_for_rate_limit(cls, source: SourceDefinition) -> None:
        previous = cls._last_fetch_at.get(source.source_id)
        if previous is not None:
            remaining = source.rate_limit_seconds - (time.monotonic() - previous)
            if remaining > 0:
                time.sleep(remaining)
        cls._last_fetch_at[source.source_id] = time.monotonic()


class RssSourceAdapter(_RateLimitedAdapter):
    """Allowlisted RSS adapter; network I/O is explicit and never used by local loaders."""

    def load(self, url: str) -> list[RawSentimentItem]:
        raise RuntimeError("RSS network ingestion is not enabled in the offline Phase 1 pipeline.")

    @staticmethod
    def parse(content: str, source: SourceDefinition) -> FetchResult:
        try:
            entries = _parse_feed_entries(content)
        except Exception as exc:
            return FetchResult(source.source_id, source.source_name, "failed", 0, 0, f"parse_error:{exc.__class__.__name__}", [])
        items = []
        for index, entry in enumerate(entries[: source.max_items], 1):
            text = f"{entry['title']} {entry['summary']}"
            if not source.matches(text):
                continue
            items.append(_entry_to_item(entry, source, index))
        status = "collected" if items else "no_match"
        return FetchResult(source.source_id, source.source_name, status, min(len(entries), source.max_items), len(items), None, items)

    def fetch(self, source: SourceDefinition, robots_checker: RobotsChecker | None = None) -> FetchResult:
        if not source.enabled:
            return FetchResult(source.source_id, source.source_name, "disabled", 0, 0, "source_disabled", [])
        if source.source_type != "rss":
            return FetchResult(source.source_id, source.source_name, "failed", 0, 0, "wrong_source_type", [])
        if source.respect_robots:
            allowed, reason = (robots_checker or RobotsChecker()).check(source.url, source.timeout_seconds)
            if not allowed:
                return FetchResult(source.source_id, source.source_name, "skipped_by_robots", 0, 0, reason, [])
        self._wait_for_rate_limit(source)
        try:
            response = httpx.get(source.url, timeout=source.timeout_seconds, headers={"User-Agent": "CrisisAgentResearchBot/0.1"}, follow_redirects=False)
            response.raise_for_status()
            return self.parse(response.text, source)
        except Exception as exc:
            return FetchResult(source.source_id, source.source_name, "failed", 0, 0, f"http_error:{exc.__class__.__name__}", [])


class HttpArticleSourceAdapter(_RateLimitedAdapter):
    def fetch(self, source: SourceDefinition, robots_checker: RobotsChecker | None = None) -> FetchResult:
        if not source.enabled:
            return FetchResult(source.source_id, source.source_name, "disabled", 0, 0, "source_disabled", [])
        if source.source_type != "article_url":
            return FetchResult(source.source_id, source.source_name, "failed", 0, 0, "wrong_source_type", [])
        if source.respect_robots:
            allowed, reason = (robots_checker or RobotsChecker()).check(source.url, source.timeout_seconds)
            if not allowed:
                return FetchResult(source.source_id, source.source_name, "skipped_by_robots", 0, 0, reason, [])
        self._wait_for_rate_limit(source)
        try:
            response = httpx.get(source.url, timeout=source.timeout_seconds, headers={"User-Agent": "CrisisAgentResearchBot/0.1"}, follow_redirects=False)
            response.raise_for_status()
            article = extract_article(response.text, source.url)
            if len(article.content.strip()) < 80:
                return FetchResult(source.source_id, source.source_name, "no_match", 1, 0, "content_too_short", [])
            item = RawSentimentItem(
                item_id=f"{source.source_id}:{source.url}",
                source_name=source.source_name,
                source_url=source.url,
                title=article.title or source.source_name,
                content=article.content,
                published_at=article.published_at or datetime.now(timezone.utc).isoformat(),
                company=source.company_keywords[0] if source.company_keywords else "unknown",
                fact_status="unverified",
            )
            if not source.matches(f"{item.title} {item.content}"):
                return FetchResult(source.source_id, source.source_name, "no_match", 1, 0, "keyword_not_matched", [])
            return FetchResult(source.source_id, source.source_name, "collected", 1, 1, None, [item])
        except Exception as exc:
            return FetchResult(source.source_id, source.source_name, "failed", 0, 0, f"http_error:{exc.__class__.__name__}", [])


def _parse_feed_entries(content: str) -> list[dict]:
    try:
        import feedparser  # type: ignore

        parsed = feedparser.parse(content)
        if getattr(parsed, "bozo", False) and not getattr(parsed, "entries", []):
            raise ValueError("invalid feed")
        return [
            {
                "title": str(entry.get("title", "")),
                "link": str(entry.get("link", "")),
                "summary": str(entry.get("summary", entry.get("description", ""))),
                "published": str(entry.get("published", entry.get("updated", ""))),
            }
            for entry in parsed.entries
        ]
    except ImportError:
        root = ET.fromstring(content)
        entries = []
        for node in root.findall(".//item") + root.findall(".//{http://www.w3.org/2005/Atom}entry"):
            def text(name):
                child = node.find(name)
                if child is None:
                    child = node.find(f"{{http://www.w3.org/2005/Atom}}{name}")
                return child.text.strip() if child is not None and child.text else ""
            entries.append({"title": text("title"), "link": text("link"), "summary": text("description") or text("summary"), "published": text("pubDate") or text("published") or text("updated")})
        return entries


def _entry_to_item(entry: dict, source: SourceDefinition, index: int) -> RawSentimentItem:
    return RawSentimentItem(
        item_id=f"{source.source_id}:{entry.get('link') or index}",
        source_name=source.source_name,
        source_url=entry.get("link", ""),
        title=entry.get("title", "").strip(),
        content=entry.get("summary", "").strip(),
        published_at=_normalize_published(entry.get("published", "")),
        company=source.company_keywords[0] if source.company_keywords else "unknown",
        fact_status="unverified",
    )


def _normalize_published(value: str) -> str:
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        return str(value or "")


def load_local_items(path: str | Path) -> list[RawSentimentItem]:
    suffix = Path(path).suffix.lower()
    if suffix == ".json":
        return LocalJsonSourceAdapter().load(path)
    if suffix == ".csv":
        return LocalCsvSourceAdapter().load(path)
    raise ValueError("Only local .json and .csv sentiment inputs are supported.")
