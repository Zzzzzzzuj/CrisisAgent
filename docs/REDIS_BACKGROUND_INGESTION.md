# Redis Background Ingestion

## Purpose

Synchronous ingestion remains available for offline debugging. A request with
`background=true` creates an `IngestionRun` in `queued` state and dispatches it
through Redis/RQ. Redis is required for that background path and is never used
as the business-data store: the IngestionRun repository remains the source of
truth for API status, source results, clusters, and errors.

## Configuration

```env
REDIS_URL=redis://localhost:6379/0
INGESTION_QUEUE_NAME=crisis-ingestion
INGESTION_JOB_TIMEOUT_SECONDS=300
```

Install the existing `redis` and `rq` dependencies, start Redis, then start a
separate worker:

```powershell
docker compose --profile rq up -d redis ingestion-worker
python scripts/run_ingestion_worker.py
```

`INGESTION_WORKER_CLASS=auto` is the default. On Windows it selects RQ
`SimpleWorker`, because the normal RQ `Worker` relies on `os.fork()`, which
Windows does not provide. On Linux and Docker, `auto` selects the normal RQ
`Worker`. Set the value to `simple` or `worker` only when an explicit local
override is needed. `SimpleWorker` is for Windows development and smoke tests;
it is not the production worker model.

For a Windows local smoke, start only Redis, then run the worker in a separate
PowerShell window:

```powershell
docker compose --profile rq up -d redis
$env:REDIS_URL="redis://localhost:6379/0"
$env:INGESTION_WORKER_CLASS="auto"
python scripts/run_ingestion_worker.py
```

The startup line should name `SimpleWorker`. In Docker/Linux, use
`docker compose --profile rq up -d redis ingestion-worker`; `auto` selects the
normal RQ `Worker` there.

The worker does not start FastAPI, call an LLM, or enable live fetching.

## API behavior

`POST /api/ingestion/run` accepts `background` (default `false`).

- `background=false`: executes synchronously and returns the completed run.
- `background=true`: requires Redis, returns `queued`, `execution_mode=background`,
  `queue_backend=redis`, and an RQ `job_id`.
- Redis configuration, connectivity, or enqueue failures return HTTP 503. The
  API does not silently fall back to an in-process worker.
- `dry_run=true` is intentionally synchronous and never accesses a source.

Poll `GET /api/ingestion/runs/{run_id}` for `queued`, `running`, `completed`,
`partial`, or `failed`. The frontend never reads Redis job status directly.

## Safety and authorization

Only `admin` and `operator` may create ingestion runs. `viewer` and
`legal_reviewer` denials are audited. `live_fetch=true` still requires
`ENABLE_API_LIVE_FETCH=true`; queueing cannot bypass the existing HTTPS,
allowlist, robots, timeout, rate-limit, or `max_items` controls. No path
automatically publishes a statement.

Audit actions include `ingestion.run.queued`, `ingestion.run.started`,
`ingestion.run.completed`, retry/dead-letter transitions, and recovery actions,
with execution mode, queue backend, job ID, and final status metadata.

## Local and CI boundary

The ordinary test suite injects fake queue behavior and does not require a
network Redis instance or cloud service. Docker Compose keeps Redis and the
worker behind the `rq` profile. GitHub CI remains offline/fake-queue based.

## Current limits

See [Queue Reliability](QUEUE_RELIABILITY.md) for bounded retry, dead-letter,
timeout, worker-heartbeat, and stuck-run recovery behavior. JSON product
storage remains the default business storage; cancellation, priority queues,
autoscaling, and alerting are still future work.

## Interview version

> I separated dispatch state from business state. Redis/RQ only carries a
> background ingestion job; the persisted IngestionRun is the source of truth.
> The API returns a queued run immediately, the worker updates its lifecycle,
> and the UI polls our own run endpoint rather than exposing Redis internals.
> Redis failure is explicit with a 503 and audit record, never an invisible
> in-process fallback.
