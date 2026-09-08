from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVENT_AGENT_RUN_STORE_PATH = PROJECT_ROOT / "data" / "event_agent_runs.runtime.json"


class JsonEventAgentRunStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.getenv("EVENT_AGENT_RUN_STORE_PATH", DEFAULT_EVENT_AGENT_RUN_STORE_PATH))

    def list_runs(self, event_id: str | None = None) -> list[dict[str, Any]]:
        runs = self._load()
        if event_id is not None:
            runs = [run for run in runs if run.get("event_id") == event_id]
        return list(reversed(runs))

    def get_latest(self, event_id: str) -> dict[str, Any] | None:
        runs = self.list_runs(event_id)
        return runs[0] if runs else None

    def create(self, run: dict[str, Any]) -> dict[str, Any]:
        runs = self._load()
        payload = dict(run)
        payload.setdefault("agent_run_id", str(uuid4()))
        payload.setdefault("created_at", _now())
        runs.append(payload)
        self._save(runs)
        return payload

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("runs"), list):
            raise ValueError("Event agent run store must contain a runs array.")
        return [item for item in payload["runs"] if isinstance(item, dict)]

    def _save(self, runs: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"runs": runs}, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )


def get_event_agent_run_store() -> JsonEventAgentRunStore:
    return JsonEventAgentRunStore()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
