from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASE_MEMORY_PATH = ROOT / "data" / "case_memories.runtime.json"


class JsonCaseMemoryStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.getenv("CASE_MEMORY_STORE_PATH", DEFAULT_CASE_MEMORY_PATH))

    def list_memories(self, *, entity_id=None, crisis_type=None, risk_level=None, tag=None,
                      include_archived=False, limit=20) -> list[dict[str, Any]]:
        values = self._load()
        filtered = []
        for item in values:
            if not include_archived and item.get("archived", False):
                continue
            if entity_id is not None and item.get("entity_id") != entity_id:
                continue
            if crisis_type is not None and item.get("crisis_type") != crisis_type:
                continue
            if risk_level is not None and item.get("risk_level") != risk_level:
                continue
            if tag is not None and tag not in item.get("tags", []):
                continue
            filtered.append(item)
        return list(reversed(filtered[-limit:]))

    def get(self, memory_id: str) -> dict[str, Any] | None:
        return next((item for item in self._load() if item.get("memory_id") == memory_id), None)

    def create(self, payload: dict[str, Any], *, actor_id: str, owner_id: str) -> dict[str, Any]:
        now = _now()
        value = {
            **payload,
            "memory_id": str(uuid4()),
            "created_by": actor_id,
            "owner_id": owner_id,
            "created_at": now,
            "updated_at": now,
            "archived": False,
        }
        values = self._load()
        values.append(value)
        self._save(values)
        return value

    def update(self, memory_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
        values = self._load()
        for index, current in enumerate(values):
            if current.get("memory_id") != memory_id:
                continue
            value = {**current, **changes, "updated_at": _now()}
            values[index] = value
            self._save(values)
            return value
        return None

    def archive(self, memory_id: str) -> dict[str, Any] | None:
        return self.update(memory_id, {"archived": True})

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("memories"), list):
            raise ValueError("Case memory store must contain a memories array.")
        return [item for item in payload["memories"] if isinstance(item, dict)]

    def _save(self, values: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"memories": values}, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )


def get_case_memory_store() -> JsonCaseMemoryStore:
    return JsonCaseMemoryStore()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
