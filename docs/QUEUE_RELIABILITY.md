# Queue Reliability

Background ingestion keeps Redis as a dispatch layer only. The persisted
IngestionRun remains the product source of truth for attempts, errors, final
status, and recovery history.

## Retry and dead letter

`INGESTION_JOB_MAX_RETRIES` defaults to `2`; failures increment `retry_count`
on the same run and schedule the same `run_id` again after
`INGESTION_JOB_RETRY_DELAY_SECONDS`. On exhaustion, the run becomes `failed`,
records `last_error` and `dead_lettered_at`, and is also sent to the
`crisis-ingestion-dead-letter` Redis queue for future operator inspection. It
is never automatically re-executed from dead letter.

`INGESTION_JOB_TIMEOUT_SECONDS` is passed to RQ and persisted on the run. A
timeout is audited as `ingestion.run.timeout`; other failures are retried or
dead-lettered by the same policy.

## Heartbeat and recovery

Workers update `worker:ingestion:{worker_id}:heartbeat` Redis keys at job start
and completion. `GET /api/ingestion/workers` lets admin, operator, and viewer
inspect worker ID, queue, status, and last-seen time. The Workbench has a manual
refresh only; it does not poll continuously.

Recover stale work safely by default:

```powershell
python scripts/recover_stuck_ingestion_runs.py --max-age-seconds 600
python scripts/recover_stuck_ingestion_runs.py --mode mark-failed --apply
python scripts/recover_stuck_ingestion_runs.py --mode requeue --apply
```

`requeue` requires Redis. Recovery writes an audit record and never calls an
LLM or enables live fetch beyond the existing server-side guard.

## Limits

This is a minimal reliability layer. It does not yet provide cancellation,
priority queues, distributed locking for JSON business storage, delayed-job
monitoring, alert delivery, or worker autoscaling. Windows uses SimpleWorker
for smoke; Docker/Linux uses RQ Worker.

## Interview version

> I separated queue reliability from business truth: Redis schedules attempts,
> while IngestionRun persists retry count, errors, timeout configuration,
> dead-letter state, and recovery reason. This makes retries observable to the
> API and UI instead of hiding them in a queue implementation.
