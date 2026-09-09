from __future__ import annotations

import os
from datetime import timedelta
from typing import Any


class IngestionQueueUnavailable(RuntimeError):
    """Raised when the required Redis/RQ dispatch layer is unavailable."""


def _queue_settings() -> tuple[str, str, int]:
    redis_url = os.getenv("REDIS_URL", "").strip()
    if not redis_url:
        raise IngestionQueueUnavailable("REDIS_URL is required for background ingestion runs.")
    queue_name = os.getenv("INGESTION_QUEUE_NAME", "crisis-ingestion").strip() or "crisis-ingestion"
    timeout_seconds = job_timeout_seconds()
    return redis_url, queue_name, timeout_seconds


def job_timeout_seconds() -> int:
    try:
        timeout_seconds = int(os.getenv("INGESTION_JOB_TIMEOUT_SECONDS", "300"))
    except ValueError as exc:
        raise IngestionQueueUnavailable("INGESTION_JOB_TIMEOUT_SECONDS must be an integer.") from exc
    if timeout_seconds <= 0:
        raise IngestionQueueUnavailable("INGESTION_JOB_TIMEOUT_SECONDS must be positive.")
    return timeout_seconds


def reliability_settings() -> tuple[int, int, str]:
    try:
        max_retries = int(os.getenv("INGESTION_JOB_MAX_RETRIES", "2"))
        retry_delay = int(os.getenv("INGESTION_JOB_RETRY_DELAY_SECONDS", "5"))
    except ValueError as exc:
        raise IngestionQueueUnavailable("Ingestion retry settings must be integers.") from exc
    if max_retries < 0 or retry_delay < 0:
        raise IngestionQueueUnavailable("Ingestion retry settings must be non-negative.")
    queue_name = os.getenv("INGESTION_QUEUE_NAME", "crisis-ingestion").strip() or "crisis-ingestion"
    return max_retries, retry_delay, f"{queue_name}-dead-letter"


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


def schedule_ingestion_retry(run_id: str, payload: dict[str, Any], user_context: dict[str, Any], delay_seconds: int) -> str:
    """Requeue the same business run without allocating a new run ID."""
    _, queue_name, timeout_seconds = _queue_settings()
    try:
        from rq import Queue
        from backend.api.ingestion_worker import run_ingestion_job

        queue = Queue(queue_name, connection=get_redis_connection())
        job = queue.enqueue_in(timedelta(seconds=delay_seconds), run_ingestion_job, run_id, payload, user_context, job_timeout=timeout_seconds)
        return str(job.id)
    except IngestionQueueUnavailable:
        raise
    except Exception as exc:
        raise IngestionQueueUnavailable(f"Redis retry enqueue failed: {exc}") from exc


def record_dead_letter(run_id: str, error: str) -> dict[str, str]:
    return {"run_id": run_id, "error": error}


def enqueue_dead_letter(run_id: str, error: str) -> str:
    """Keep a lightweight Redis dead-letter record for later operator inspection."""
    _, _, dead_letter_queue = reliability_settings()
    try:
        from rq import Queue

        job = Queue(dead_letter_queue, connection=get_redis_connection()).enqueue(record_dead_letter, run_id, error)
        return str(job.id)
    except IngestionQueueUnavailable:
        raise
    except Exception as exc:
        raise IngestionQueueUnavailable(f"Redis dead-letter enqueue failed: {exc}") from exc
