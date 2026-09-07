import csv
import json
from pathlib import Path
from typing import Iterable

from .schemas import RawSentimentItem


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


class RssSourceAdapter:
    """Reserved adapter; Phase 1 intentionally never performs network I/O."""

    def load(self, url: str) -> list[RawSentimentItem]:
        raise RuntimeError("RSS network ingestion is not enabled in the offline Phase 1 pipeline.")


def load_local_items(path: str | Path) -> list[RawSentimentItem]:
    suffix = Path(path).suffix.lower()
    if suffix == ".json":
        return LocalJsonSourceAdapter().load(path)
    if suffix == ".csv":
        return LocalCsvSourceAdapter().load(path)
    raise ValueError("Only local .json and .csv sentiment inputs are supported.")
