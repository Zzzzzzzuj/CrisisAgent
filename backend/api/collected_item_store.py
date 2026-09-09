from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COLLECTED_ITEM_STORE_PATH = PROJECT_ROOT / "data" / "collected_items.runtime.json"


class JsonCollectedItemStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.getenv("COLLECTED_ITEM_STORE_PATH", DEFAULT_COLLECTED_ITEM_STORE_PATH))

    def save_many(self, items: list[dict[str, Any]]) -> None:
        existing = self._load()
        known = {(item.get("source_id"), item.get("content_hash")) for item in existing}
        for item in items:
            key = (item.get("source_id"), item.get("content_hash"))
            if key not in known:
                existing.append(item)
                known.add(key)
        self._save(existing)

    def list_items(self, *, source_id: str | None = None, ingestion_run_id: str | None = None, status: str | None = None, entity_id: str | None = None, provider: str | None = None, monitor_run_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        items = self._load()
        filtered = [
            item for item in items
            if (source_id is None or item.get("source_id") == source_id)
            and (ingestion_run_id is None or item.get("ingestion_run_id") == ingestion_run_id)
            and (status is None or item.get("status") == status)
            and (entity_id is None or item.get("entity_id") == entity_id)
            and (provider is None or item.get("provider") == provider)
            and (monitor_run_id is None or item.get("monitor_run_id") == monitor_run_id)
        ]
        return list(reversed(filtered[-limit:]))

    def get(self, item_id: str) -> dict[str, Any] | None:
        return next((item for item in self._load() if item.get("item_id") == item_id), None)

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ValueError("Collected item store must contain an items array.")
        return [item for item in payload["items"] if isinstance(item, dict)]

    def _save(self, items: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"items": items}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def get_collected_item_store() -> JsonCollectedItemStore:
    return JsonCollectedItemStore()
