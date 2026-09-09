from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.api.ingestion_execution import api_live_fetch_enabled
from backend.api.live_monitor_execution import execute_monitor_payload
from backend.api.live_monitor_store import get_live_monitor_run_store
from backend.api.watchlist_store import get_watchlist_store


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def build_request(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "entity_ids": [args.entity_id] if args.entity_id else None,
        "providers": [args.provider] if args.provider else None,
        "lookback_minutes": 60,
        "max_items_per_entity": 10,
        "background": args.background,
        "live_fetch": args.live_fetch,
    }


def run_once(args: argparse.Namespace) -> dict[str, Any]:
    enabled = get_watchlist_store().list(enabled=True)
    if args.entity_id and not any(item.get("entity_id") == args.entity_id for item in enabled):
        raise ValueError(f"enabled watchlist entity not found: {args.entity_id}")
    if not enabled:
        raise ValueError("no enabled watchlist entities")
    if args.live_fetch and not api_live_fetch_enabled():
        raise RuntimeError("live fetch is disabled; set ENABLE_API_LIVE_FETCH=true")
    payload = build_request(args)
    run_id = str(uuid4())
    if args.background:
        from backend.api.ingestion_queue import submit_live_monitor_job

        get_live_monitor_run_store().save({
            "monitor_run_id": run_id, "status": "queued", "live_fetch": args.live_fetch,
            "background": True, "entity_count": len(enabled), "provider_count": 1,
            "source_results": [], "item_count": 0, "cluster_count": 0, "alert_count": 0,
            "automatic_publish": False, "error": None,
        })
        job_id = submit_live_monitor_job(run_id, payload, {"id": "scheduled-monitor", "role": "operator"})
        return {"monitor_run_id": run_id, "status": "queued", "job_id": job_id, "signal_count": 0, "alert_count": 0, "automatic_publish": False}
    result = execute_monitor_payload(payload, run_id)
    get_live_monitor_run_store().save(result)
    return {"monitor_run_id": run_id, "status": result["status"], "signal_count": result["item_count"], "alert_count": result["alert_count"], "automatic_publish": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a bounded Watchlist live monitor cycle.")
    parser.add_argument("--interval-minutes", type=float, default=float(os.getenv("LIVE_MONITOR_INTERVAL_MINUTES", "30")))
    parser.add_argument("--once", action="store_true", help="run one cycle and exit")
    parser.add_argument("--entity-id")
    parser.add_argument("--provider", choices=["gdelt_doc", "news_api", "rss"])
    parser.add_argument("--background", type=parse_bool, default=False)
    parser.add_argument("--live-fetch", type=parse_bool, default=False)
    args = parser.parse_args(argv)
    if args.interval_minutes <= 0:
        parser.error("--interval-minutes must be positive")
    if not args.once and os.getenv("ENABLE_SCHEDULED_LIVE_MONITOR", "false").lower() != "true":
        print("Scheduled live monitoring is disabled. Use --once for a single cycle or set ENABLE_SCHEDULED_LIVE_MONITOR=true.")
        return 0
    try:
        while True:
            try:
                print(run_once(args))
            except Exception as exc:
                print({"status": "failed", "error": str(exc), "automatic_publish": False})
                if args.once:
                    return 1
            if args.once:
                return 0
            time.sleep(args.interval_minutes * 60)
    except KeyboardInterrupt:
        print("Scheduled live monitoring stopped.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
