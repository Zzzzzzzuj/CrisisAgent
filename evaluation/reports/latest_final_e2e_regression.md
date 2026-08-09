# CrisisAgent Final End-to-End Regression

- Phase: 5C
- Branch: `test/final-e2e-regression`
- Tested HEAD: `686415d`
- Tested mode: offline/mock regression, with targeted stubs for Legal RAG/Gate/LLM failure paths.
- Working tree note: this regression found and fixed one Legal Agent trace metadata issue before final validation: retriever exception now records `fallback_used=true`. This is a trace/fallback metadata fix, not a Gate/Reranker/Retriever algorithm change.

## Scope

This regression checks that the following layers still work together:

- Fixed Workflow
- Dynamic Runtime
- AgentState / trace / checkpoint persistence
- Legal Agent Retrieval Need Gate metadata
- RAG metadata propagation
- Human Gate approve/reject paths
- Dashboard build compatibility

Frozen algorithm modules were not changed:

- Retrieval Need Gate rules: unchanged
- Reranker v2 weights/domain signals: unchanged
- Hybrid weights: unchanged
- Threshold / Top-K / Embedding / Knowledge Base / Query Rewrite / Prompt: unchanged

## Real Call Chain Audit

### Fixed Workflow

Actual route:

`POST /api/crisis/run`

Actual order in `backend/workflow.py`:

1. Agent A / Sentiment
2. Agent C / Writer v1
3. Agent D / RedTeam
4. Agent B / Legal
5. Agent C / Writer v2
6. Agent E / Decision
7. `save_session()`
8. `CrisisRunResponse`

Legal Agent inner flow in LLM mode:

`_retrieve_legal_context()` -> Retrieval Need Gate -> skip/retrieve -> RAG context -> Legal prompt -> LLM parse/validate/normalize -> fallback to mock on LLM failure.

### Dynamic Runtime

Actual route:

`POST /api/dynamic/run`

Actual order:

1. Planner
2. Plan Validator
3. AgentState initialization
4. Executor
5. Agents
6. Runtime evaluation
7. Human policy
8. Checkpoint persistence
9. Response trace enhancement

Legal RAG metadata propagation:

- `legal_agent.get_last_rag_info()` returns `gate`, `retrieval_skipped`, `retrieval_executed`, `retrieval_status`, `sources`, `scores`, `rerank_scores`, `count`, `fallback_used`.
- `backend/core/executor.py` deep-copies this into `trace_item["rag"]` for the `legal` node.
- `backend/workflow.py` reads the same metadata for fixed workflow Agent B trace.

## API Routes Checked

- `GET /health`
- `POST /api/crisis/run`
- `GET /api/crisis/sessions`
- `GET /api/crisis/sessions/{session_id}`
- `POST /api/dynamic/run`
- `GET /api/dynamic/sessions`
- `GET /api/dynamic/{session_id}`
- `GET /api/dynamic/{session_id}/metrics`
- `POST /api/dynamic/{session_id}/approve`
- `POST /api/dynamic/{session_id}/reject`

Missing dynamic session returns `404`.

Missing dynamic `event` field returns `422`.

## Regression Results

### CASE A: Fixed Workflow

Command:

```powershell
$env:AGENT_MODE='mock'; C:\Users\19726\Documents\CrisisAgent\.venv\Scripts\python.exe scripts\test_workflow.py
```

Result:

- Status: PASS
- `final_statement`: present
- `scores`: present
- `agent_trace`: present
- Agent order: `Agent A -> Agent C -> Agent D -> Agent B -> Agent C -> Agent E`
- API schema: unchanged (`session_id`, `final_statement`, `scores`, `agent_trace`)

### CASE B: Dynamic High-Risk Crisis

Command:

```powershell
C:\Users\19726\Documents\CrisisAgent\.venv\Scripts\python.exe scripts\test_dynamic_runtime.py
```

Result:

- Status: PASS
- `executed_agents`: `sentiment, writer, redteam, legal, writer_v2, decision`
- `failed_agents`: empty
- `decision status`: success
- `agent_loop status`: completed
- `agent_loop evaluation_passed`: true

Additional targeted Dynamic Legal LLM-path smoke:

- Legal Agent executed successfully.
- Gate result: `need_rag=true`
- Retriever: `retrieval_executed=true`
- Retrieval status: `executed_with_hits`
- Sources: `["food_safety.md"]`
- RAG metadata entered dynamic `execution_trace`.

### CASE C: Gate Skip

Stubbed Gate:

- `need_rag=false`

Observed:

- Retriever call count: `0`
- `retrieval_skipped=true`
- `retrieval_executed=false`
- `retrieval_status=skipped_by_gate`
- `fallback_used=false`
- Legal context: empty string

Result: PASS

### CASE D: Gate Hit

Stubbed Gate:

- `need_rag=true`

Stubbed Retriever:

- Returns one source: `food_safety.md`

Observed:

- Retriever call count: `1`
- `retrieval_executed=true`
- `retrieval_skipped=false`
- `retrieval_status=executed_with_hits`
- `sources=["food_safety.md"]`
- `count=1`
- `scores` and `rerank_scores` preserved

Result: PASS

### CASE E: Gate True + No Hit

Stubbed Gate:

- `need_rag=true`

Stubbed Retriever:

- Returns empty `context`, `sources`, and `chunks`

Observed:

- Retriever call count: `1`
- `retrieval_executed=true`
- `retrieval_skipped=false`
- `retrieval_status=executed_no_hit`
- `count=0`
- `sources=[]`

Result: PASS

### CASE F: Retriever Exception / Fallback Metadata

Stubbed Gate:

- `need_rag=true`

Stubbed Retriever:

- Raises `RuntimeError`

Observed after Phase 5C metadata fix:

- Legal Agent continues with empty context.
- `retrieval_executed=true`
- `retrieval_skipped=false`
- `retrieval_status=retrieval_error`
- `fallback_used=true`
- Gate skip remains `fallback_used=false`.

Result: PASS

### CASE G: LLM Failure

Stubbed Legal LLM:

- Invalid JSON / missing required fields

Observed:

- Legal Agent falls back to mock business output.
- Output schema remains complete:
  - `legal_risks`
  - `safe_points`
  - `revision_advice`
  - `public_opinion_suggestions`
  - `integrated_revision_tasks`
  - `legal_safety_score_hint`
  - `review_summary`

Existing pytest coverage also verifies:

- Missing API key fallback
- Invalid JSON fallback
- LLM parse/validation failure fallback

Result: PASS

### CASE H: Historical Session / Missing Gate Fields

Frontend compatibility is handled in `frontend/src/components/AdvancedAnalysis.vue` using optional chaining and default labels:

- Missing `rag.gate`: displays `Unknown` / fallback explanation.
- Missing `retrieval_status`: displays `Unknown`.
- Missing arrays: displays `None`.
- Raw RAG JSON remains available.

Frontend build passed.

Result: PASS

## API / Persistence / Human Gate

In-memory ASGI API regression was used to avoid writing persistent checkpoint files during the final regression.

Observed:

- `GET /health`: `200`
- `POST /api/crisis/run`: `200`
- `GET /api/crisis/sessions`: `200`
- `POST /api/dynamic/run`: `200`
- `GET /api/dynamic/{session_id}`: `200`
- `GET /api/dynamic/sessions`: `200`
- `GET /api/dynamic/{session_id}/metrics`: `200`
- `GET /api/dynamic/not-exist`: `404`
- `POST /api/dynamic/run` without `event`: `422`

Human Gate:

- A completed session correctly rejects approve/reject with `400`.
- With policy forced to `WAITING_HUMAN`:
  - approve returns `200`, status `resumed`
  - reject returns `200`, status `failed`
  - reviewer/comment/timestamp are preserved in approval metadata

Persistence:

- Dynamic session save/list/detail behavior was validated using in-memory checkpoint stubs.
- No local checkpoint file was modified during the API regression smoke.

## Trace Fields Checked

Legal RAG trace contains:

- `gate`
- `retrieval_skipped`
- `retrieval_executed`
- `retrieval_status`
- `sources`
- `chunks`
- `scores`
- `rerank_scores`
- `count`
- `fallback_used`

Dynamic Runtime keeps RAG metadata only on Legal Agent trace. Other agents are not polluted with Legal RAG metadata.

## Test Results

### Pytest Collect

Command:

```powershell
C:\Users\19726\Documents\CrisisAgent\.venv\Scripts\python.exe -m pytest --collect-only -q
```

Result:

- Collected: `398`

### Pytest Full

Command:

```powershell
C:\Users\19726\Documents\CrisisAgent\.venv\Scripts\python.exe -m pytest -q
```

Result:

- Passed: `398`
- Failed: `0`
- Skipped: `0`

### Script Smoke

`scripts/test_workflow.py`:

- Result: PASS

`scripts/test_dynamic_runtime.py`:

- Result: PASS
- `decision status = success`
- `agent_loop evaluation_passed = True`

### Frontend Build

Command:

```powershell
cd frontend
npm run build
```

Result:

- PASS
- Vite transformed 87 modules and built production assets.

Frontend lint/test:

- Not configured in `frontend/package.json`.

## Final Status

Final E2E Regression: PASS

No frozen algorithm changes:

- Gate rules modified: no
- Reranker modified: no
- Retriever parameters modified: no
- Hybrid / threshold / Top-K / Embedding / Knowledge Base / Query Rewrite / Prompt modified: no

## Known Limitations

1. `legal_agent._LAST_RAG_INFO` is module-level state. It is acceptable for this local serial demo, but concurrent requests can still risk trace isolation issues.
2. Reranker v2 is hand-written domain-aware rules, not a trained cross-encoder or learned reranking model.
3. Gate v3 passed frozen Challenge v3, but still had real FP/FN in that validation. It is not perfect.
4. Offline regression does not cover real BGE model download/cache failures or real LLM network stability.
5. The current LLM layer has fallback behavior, but no automatic retry policy.
