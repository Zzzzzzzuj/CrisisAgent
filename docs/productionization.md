# Productionization Notes

This document describes the local PostgreSQL runtime path for CrisisAgent. It does not change Agent logic, prompts, API routes, or the frontend UI.

## Storage Modes

CrisisAgent keeps JSON checkpoint storage as the default offline-safe mode:

```env
CHECKPOINT_STORAGE=json
```

To run the production-style checkpoint path, use PostgreSQL:

```env
CHECKPOINT_STORAGE=postgres
DATABASE_URL=postgresql+psycopg://crisis_agent:crisis_agent_dev_password@localhost:5432/crisis_agent
```

Do not commit real passwords or local `.env` files.

## Start Local PostgreSQL

Start the local PostgreSQL service with Docker Compose:

```bash
docker compose up -d postgres
```

Check the service:

```bash
docker compose ps
```

The compose file creates:

- database: `crisis_agent`
- user: `crisis_agent`
- password: `crisis_agent_dev_password`
- port: `5432`

These credentials are for local development only.

## Run Migrations

Set the database URL, then run Alembic:

PowerShell:

```powershell
$env:CHECKPOINT_STORAGE="postgres"
$env:DATABASE_URL="postgresql+psycopg://crisis_agent:crisis_agent_dev_password@localhost:5432/crisis_agent"
python -m alembic upgrade head
```

Bash:

```bash
export CHECKPOINT_STORAGE=postgres
export DATABASE_URL=postgresql+psycopg://crisis_agent:crisis_agent_dev_password@localhost:5432/crisis_agent
python -m alembic upgrade head
```

Expected tables include:

- `crisis_sessions`
- `agent_checkpoints`
- `agent_traces`
- `approvals`
- `evaluations`
- `audit_logs`

## Start Backend With PostgreSQL

For local development, either export environment variables in the shell or place them in `backend/.env`:

```env
AGENT_MODE=mock
CHECKPOINT_STORAGE=postgres
DATABASE_URL=postgresql+psycopg://crisis_agent:crisis_agent_dev_password@localhost:5432/crisis_agent
RUNTIME_MODE=sync
```

Start FastAPI:

```bash
uvicorn backend.main:app --reload
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

## Dynamic Runtime Modes

The default runtime mode remains synchronous and is safest for local tests:

```env
RUNTIME_MODE=sync
```

In sync mode, `POST /api/dynamic/run` executes the Dynamic Runtime before returning.

For production-style long-running requests, enable async mode:

```env
RUNTIME_MODE=async
```

In async mode, `POST /api/dynamic/run` only:

- creates a session
- saves an initial checkpoint
- marks the state as `QUEUED`
- submits a background worker task
- returns `session_id` immediately

The current local implementation uses an in-process worker pool so the project can run without Redis during development. The queue boundary is isolated in `backend/core/runtime_tasks.py`, so it can be replaced with Redis/RQ or Celery later without changing Agent logic or API routes.

Known limits of the in-process worker:

- queued tasks that have not started can be lost if the backend process restarts
- multiple backend processes do not share the same in-memory worker pool
- production deployment should replace the local worker with Redis/RQ, Celery, or another durable queue

Dynamic task states include:

- `CREATED`
- `QUEUED`
- `RUNNING`
- `WAITING_HUMAN`
- `COMPLETED`
- `FAILED`
- `REJECTED`

Use the session detail endpoint to poll progress:

```bash
curl http://127.0.0.1:8000/api/dynamic/<session_id>
```

If a worker fails, the runtime writes a `runtime_worker` failure trace and saves the failed checkpoint.

## Verify Dynamic Runtime

Create a dynamic crisis case.

PowerShell:

```powershell
$body = @{ event = "某食品品牌被曝光使用过期原料，消费者要求监管介入。" } | ConvertTo-Json
$bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
$result = Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/dynamic/run `
  -Body $bytes `
  -ContentType "application/json; charset=utf-8"

$result.session_id
$result.status
```

List sessions:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/dynamic/sessions
```

Inspect one session:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/dynamic/$($result.session_id)"
```

## Verify Human Review

If a case returns `waiting_human`, approve it:

```powershell
$approveBody = @{ reviewer = "enterprise-reviewer"; comment = "Approved for release." } | ConvertTo-Json
$approveBytes = [System.Text.Encoding]::UTF8.GetBytes($approveBody)

Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/dynamic/$($result.session_id)/approve" `
  -Body $approveBytes `
  -ContentType "application/json; charset=utf-8"
```

Reject works the same way:

```powershell
$rejectBody = @{ reviewer = "enterprise-reviewer"; comment = "Reject and revise." } | ConvertTo-Json
$rejectBytes = [System.Text.Encoding]::UTF8.GetBytes($rejectBody)

Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/dynamic/$($result.session_id)/reject" `
  -Body $rejectBytes `
  -ContentType "application/json; charset=utf-8"
```

## Auth And RBAC

Local demo mode keeps authentication disabled by default:

```env
AUTH_ENABLED=false
```

When `AUTH_ENABLED=false`, existing API calls keep working and `approve` / `reject` can still pass a demo `reviewer` value in the request body.

Enable authentication for production-style review flows:

```env
AUTH_ENABLED=true
SECRET_KEY=<use-a-strong-random-secret>
JWT_EXPIRE_MINUTES=1440
```

Roles:

- `operator`: creates crisis cases and can view cases created by that user
- `legal_reviewer`: can approve or reject `WAITING_HUMAN` cases
- `admin`: can view all cases and approve or reject cases

`SECRET_KEY` must come from the environment. Do not commit real secrets.

Create initial users with a one-off local script or admin console. The password must be hashed with the project helper; do not insert plaintext passwords:

```powershell
$script = @'
from backend.auth import hash_password
from backend.db.models import User
from backend.db.session import get_session_factory

with get_session_factory()() as db:
    db.add(User(username="legal-reviewer", password_hash=hash_password("change-me"), role="legal_reviewer"))
    db.commit()
'@
$script | python -
```

Login:

```powershell
$loginBody = @{ username = "legal-reviewer"; password = "change-me" } | ConvertTo-Json
$token = (Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/auth/login `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($loginBody)) `
  -ContentType "application/json; charset=utf-8").access_token
```

Check current user:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/auth/me `
  -Headers @{ Authorization = "Bearer $token" }
```

Authenticated approve:

```powershell
$approveBody = @{ comment = "Approved for release." } | ConvertTo-Json
Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/dynamic/<session_id>/approve" `
  -Headers @{ Authorization = "Bearer $token" } `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($approveBody)) `
  -ContentType "application/json; charset=utf-8"
```

When auth is enabled, `operator` users receive `403` for approve/reject. `legal_reviewer` and `admin` approvals record:

- `reviewer_id`
- `reviewer_username`
- `reviewer_role`

Audit logs use the authenticated username as `actor`; they no longer rely on the default `human` reviewer in authenticated mode.

## Verify Database Records

Use `psql` inside the container:

```bash
docker compose exec postgres psql -U crisis_agent -d crisis_agent
```

Useful checks:

```sql
SELECT session_id, status, created_at
FROM crisis_sessions
ORDER BY created_at DESC
LIMIT 5;

SELECT session_id, status, created_at
FROM agent_checkpoints
ORDER BY created_at DESC
LIMIT 5;

SELECT session_id, decision, reviewer, created_at
FROM approvals
ORDER BY created_at DESC
LIMIT 5;

SELECT session_id, action, actor, created_at
FROM audit_logs
ORDER BY created_at DESC
LIMIT 5;
```

## Testing

The standard test suite remains offline-safe and does not require PostgreSQL:

```bash
python -m pytest tests
```

Repository tests use an in-memory database to verify save/load/list/delete behavior without forcing every local run to start Docker.

## Stop Local PostgreSQL

Stop the service:

```bash
docker compose down
```

Remove the local volume only if you want to delete all local PostgreSQL data:

```bash
docker compose down -v
```
