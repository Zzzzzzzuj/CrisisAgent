from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any


_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def path_lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


def load_json_object(path: Path, key: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid {key} store JSON: {path}") from exc
    values = payload.get(key, []) if isinstance(payload, dict) else []
    if not isinstance(values, list):
        raise ValueError(f"{key} store must contain an array.")
    return [item for item in values if isinstance(item, dict)]


def save_json_object(path: Path, key: str, values: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.{threading.get_ident()}.{time.time_ns()}.tmp")
    temp.write_text(json.dumps({key: values}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)
