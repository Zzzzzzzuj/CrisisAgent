from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVAL_RUN_STORE_PATH = PROJECT_ROOT / "data" / "eval_runs.runtime.json"


class JsonEvalRunStore:
    """Small, readable local store for offline Eval Center history."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.getenv("EVAL_RUN_STORE_PATH", DEFAULT_EVAL_RUN_STORE_PATH))

    def save(self, run: dict[str, Any]) -> None:
        runs = self._load()
        runs.append(run)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"runs": runs}, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        runs = self._load()
        return list(reversed(runs[-limit:]))

    def get(self, eval_run_id: str) -> dict[str, Any] | None:
        return next((run for run in self._load() if run.get("eval_run_id") == eval_run_id), None)

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("runs"), list):
            raise ValueError("Eval run store must contain a runs array.")
        return [item for item in payload["runs"] if isinstance(item, dict)]


def get_eval_run_store() -> JsonEvalRunStore:
    return JsonEvalRunStore()
