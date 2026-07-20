# CrisisAgent MVP

CrisisAgent is a FastAPI backend MVP for enterprise crisis PR workflows.

Current status:
- The workflow is fully mock/rule based.
- No real LLM is connected yet.
- `POST /api/crisis/run` remains the main execution API.
- Session storage and query APIs are available.

## Project Structure

```text
backend/
  agents/
  prompts/
  utils/
  config.py
  llm_client.py
  logger.py
  main.py
  prompt_loader.py
  schemas.py
  storage.py
  workflow.py
cases/
scripts/
.env.example
requirements.txt
README.md
```

## Install Dependencies

```bash
pip install -r requirements.txt
```

## Development Setup

For local development and testing, install the same requirements file:

```bash
pip install -r requirements.txt
```

This includes:
- Runtime dependencies for FastAPI
- Lightweight LLM infrastructure dependencies
- `pytest` for local unit tests

## Start the Server

```bash
uvicorn backend.main:app --reload
```

Available endpoints:
- Swagger UI: `http://127.0.0.1:8000/docs`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`
- Health check: `http://127.0.0.1:8000/health`

## Test the Main Workflow

Use Swagger at `http://127.0.0.1:8000/docs` and call `POST /api/crisis/run` with:

```json
{
  "event": "某食品品牌被爆使用过期原料，偷拍视频在网上传播，网友要求监管介入。"
}
```

The response keeps the same structure:
- `session_id`
- `final_statement`
- `scores`
- `agent_trace`

## Session Query APIs

- `GET /api/crisis/sessions`
- `GET /api/crisis/sessions/{session_id}`

You can first run `POST /api/crisis/run`, copy the returned `session_id`, then query the saved session.

## Local Workflow Test Script

Run from the project root:

```bash
python scripts/test_workflow.py
```

## Run Tests

Run the Agent A test file from the project root:

```bash
python -m pytest tests/test_sentiment_agent.py
```

Run the whole test directory:

```bash
python -m pytest tests
```

## Environment Configuration

Copy `.env.example` to `.env` and fill values when needed.

Example:

```env
AGENT_MODE=mock
LLM_API_KEY=
LLM_BASE_URL=
LLM_MODEL=
LLM_TIMEOUT_SECONDS=30
```

### AGENT_MODE

- `mock`
  - Default mode.
  - No LLM configuration is required.
  - The current project should keep working exactly as before.
- `llm`
  - Reserved for future LLM integration.
  - Requires `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL`.

## v0.4.1 LLM Infrastructure

This version only adds the infrastructure needed for future LLM integration:
- `backend/config.py`
- `backend/llm_client.py`
- `backend/prompt_loader.py`
- `backend/logger.py`
- `backend/utils/json_parser.py`
- `backend/prompts/*.md`

Important:
- Existing agents are still mock/rule based.
- `workflow.py` is unchanged.
- `main.py` is unchanged.
- `POST /api/crisis/run` request and response structures are unchanged.

## Future LLM Migration Path

Later, a single agent can be upgraded incrementally:

1. Load a prompt from `backend/prompts/`
2. Call `call_llm(prompt)` from `backend/llm_client.py`
3. Parse the response with `parse_llm_json(...)`
4. Map the parsed JSON back into the existing agent output schema

This keeps the workflow and API stable while replacing one agent at a time.
