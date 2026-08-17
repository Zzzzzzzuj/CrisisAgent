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

## Auth And RBAC

Local demo mode keeps authentication disabled by default:

```env
AUTH_ENABLED=false
```

When authentication is enabled, configure a deployment secret and create users in the database:

```env
AUTH_ENABLED=true
SECRET_KEY=<strong-random-secret>
AUTH_TOKEN_EXPIRE_MINUTES=480
```

Never commit a real `SECRET_KEY` or user password.

Roles:

- `operator`: creates dynamic crisis cases and can view cases they created.
- `legal_reviewer`: can approve or reject `WAITING_HUMAN` cases.
- `admin`: can approve/reject and view all dynamic cases.

Auth endpoints:

```http
POST /api/auth/login
GET /api/auth/me
```

Login request:

```json
{
  "username": "reviewer",
  "password": "<password>"
}
```

Use the returned token as:

```http
Authorization: Bearer <token>
```

When `AUTH_ENABLED=true`, dynamic approve/reject requires `legal_reviewer` or `admin`.
The runtime records the authenticated reviewer in checkpoint approval data:

- `reviewer_id`
- `reviewer_username`
- `reviewer_role`

`audit_logs.actor` also records the authenticated username instead of the demo default `human`.
When an operator creates a dynamic case, `created_by` is stored in state metadata and persisted to `crisis_sessions` for access control.

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

## LLM Reliability And Guardrails

Real LLM mode remains optional. Local tests can keep mock mode:

```env
AGENT_MODE=mock
```

For OpenAI-compatible providers, configure the provider without committing secrets:

```env
AGENT_MODE=llm
LLM_PROVIDER=openai_compatible
LLM_MODEL=<provider-model-name>
LLM_BASE_URL=<openai-compatible-base-url>
LLM_API_KEY=<your-api-key>
LLM_TIMEOUT_SECONDS=30
LLM_MAX_RETRIES=1
LLM_RETRY_BACKOFF_SECONDS=0.5
```

`LLMClient` records compact call metadata for each Agent-level request:

- provider and model
- agent name
- latency
- success or failure
- failure type
- fallback flag
- retry count
- approximate input/output size

The trace does not store API keys or full sensitive prompts.

Failure categories are:

- `timeout`
- `rate_limit`
- `provider_error`
- `invalid_json`
- `schema_validation_failed`
- `empty_response`

When JSON output is malformed, the parser attempts one lightweight repair pass for common formatting issues such as fenced JSON, extra text, trailing commas, or Python-style object literals. If repair and schema validation fail, the Agent keeps the existing mock fallback behavior and records the failure in trace.

Guardrails run outside Agent prompts and do not change Agent business logic:

- input guardrail detects prompt-injection patterns such as ignoring previous instructions, revealing system prompts, or bypassing review
- output guardrail detects dangerous final statements such as absolute commitments, unverified factual conclusions, illegal admissions, privacy leaks, or instructions to skip human review

Human Review is required when any of these conditions are met:

- high-risk event
- runtime evaluation failure or low decision score
- input/output guardrail hit
- LLM fallback observed in Agent trace

When authentication is enabled, approve/reject remains restricted to `legal_reviewer` or `admin`.

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
