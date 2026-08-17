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
```

Start FastAPI:

```bash
uvicorn backend.main:app --reload
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

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
