from __future__ import annotations

from backend.api.live_monitor_execution import execute_monitor_payload
from backend.api.live_monitor_store import get_live_monitor_run_store


def run_live_monitor_job(monitor_run_id: str, payload: dict, user_context: dict) -> dict:
    store = get_live_monitor_run_store()
    if store.get(monitor_run_id) is None:
        return {"monitor_run_id": monitor_run_id, "status": "missing"}
    result = execute_monitor_payload(payload, monitor_run_id)
    return store.update(monitor_run_id, result)
