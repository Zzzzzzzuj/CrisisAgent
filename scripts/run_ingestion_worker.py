from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.api.ingestion_queue import IngestionQueueUnavailable, _queue_settings, get_redis_connection


def resolve_worker_class(worker_class: str | None = None, *, os_name: str | None = None):
    """Select an RQ worker compatible with the local operating system."""
    configured = (worker_class or os.getenv("INGESTION_WORKER_CLASS", "auto")).strip().lower()
    if configured not in {"auto", "worker", "simple"}:
        raise ValueError("INGESTION_WORKER_CLASS must be one of: auto, worker, simple.")

    from rq import SimpleWorker, Worker

    if configured == "simple":
        return SimpleWorker
    if configured == "worker":
        return Worker
    return SimpleWorker if (os_name or os.name) == "nt" else Worker


def main() -> int:
    try:
        _, queue_name, _ = _queue_settings()
        connection = get_redis_connection()
        from rq import Queue

        worker_class = resolve_worker_class()
        print(f"Starting CrisisAgent ingestion worker for queue '{queue_name}' using {worker_class.__name__}.")
        worker_class([Queue(queue_name, connection=connection)], connection=connection).work()
        return 0
    except IngestionQueueUnavailable as exc:
        print(f"Cannot start ingestion worker: {exc}", file=sys.stderr)
        return 2
    except ImportError as exc:
        print(f"Cannot start ingestion worker: missing queue dependency ({exc}).", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"Cannot start ingestion worker: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
