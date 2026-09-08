from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUDIT_STORE_PATH = PROJECT_ROOT / "data" / "audit_logs.runtime.json"


class JsonAuditStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.getenv("AUDIT_LOG_STORE_PATH", DEFAULT_AUDIT_STORE_PATH))

    def append(self, entry: dict[str, Any]) -> dict[str, Any]:
        logs = self.list_logs(limit=100_000, newest_first=False)
        record = {"audit_id": str(uuid4()), "timestamp": datetime.now(timezone.utc).isoformat(), **entry}
        logs.append(record)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"logs": logs}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return record

    def list_logs(self, limit: int = 50, newest_first: bool = True, **filters: str | None) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        logs = [item for item in payload.get("logs", []) if isinstance(item, dict)]
        for key, value in filters.items():
            if value is not None:
                logs = [item for item in logs if item.get(key) == value]
        logs = logs[-limit:]
        return list(reversed(logs)) if newest_first else logs


def get_audit_store() -> JsonAuditStore:
    return JsonAuditStore()
