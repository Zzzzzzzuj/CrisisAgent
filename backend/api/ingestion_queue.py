from __future__ import annotations

import os
from typing import Any


class IngestionQueueUnavailable(RuntimeError):
    """Raised when the required Redis/RQ dispatch layer is unavailable."""


def _queue_settings() -> tuple[str, str, int]:
    redis_url = os.getenv("REDIS_URL", "").strip()
    if not redis_url:
        raise IngestionQueueUnavailable("REDIS_URL is required for background ingestion runs.")
    queue_name = os.getenv("INGESTION_QUEUE_NAME", "crisis-ingestion").strip() or "crisis-ingestion"
    try:
        timeout_seconds = int(os.getenv("INGESTION_JOB_TIMEOUT_SECONDS", "300"))
    except ValueError as exc:
        raise IngestionQueueUnavailable("INGESTION_JOB_TIMEOUT_SECONDS must be an integer.") from exc
    return redis_url, queue_name, timeout_seconds


def get_redis_connection():
    redis_url, _, _ = _queue_settings()
    try:
        from redis import Redis

        connection = Redis.from_url(redis_url)
        connection.ping()
        return connection
    except Exception as exc:  # Redis connection errors are normalized for the API.
        raise IngestionQueueUnavailable(f"Redis is unavailable: {exc}") from exc


def submit_ingestion_job(run_id: str, payload: dict[str, Any], user_context: dict[str, Any]) -> str:
    """Enqueue only the run identity and necessary execution input; never fallback in-process."""
    redis_url, queue_name, timeout_seconds = _queue_settings()
    del redis_url  # get_redis_connection owns the connection construction and health check.
    try:
        from rq import Queue

        from backend.api.ingestion_worker import run_ingestion_job

        queue = Queue(queue_name, connection=get_redis_connection())
        job = queue.enqueue(
            run_ingestion_job,
            run_id,
            payload,
            user_context,
            job_timeout=timeout_seconds,
        )
        return str(job.id)
    except IngestionQueueUnavailable:
        raise
    except Exception as exc:
        raise IngestionQueueUnavailable(f"Redis enqueue failed: {exc}") from exc
