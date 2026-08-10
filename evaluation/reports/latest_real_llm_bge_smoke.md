# Real DeepSeek + BGE Minimal Smoke Test

## Scope

- Test type: minimal real-model smoke test, not a reliability benchmark.
- Tested commit: `810031d`
- Branch: `test/real-llm-bge-smoke`
- Timestamp: `2026-08-09 18:55:47 +08:00`
- Python executable: `C:\Users\19726\Documents\CrisisAgent\.venv\Scripts\python.exe`
- `AGENT_MODE`: `llm`
- `EMBEDDING_MODEL`: `bge`
- LLM provider: OpenAI-compatible API
- LLM model: `deepseek-v4-flash`
- LLM base URL host: `api.deepseek.com`
- BGE model: `BAAI/bge-small-zh`
- `sentence-transformers`: `5.7.0`
- `HF_HOME`: `C:\Users\19726\Documents\hf-cache`

No API key, prompt body, or sensitive environment value is recorded in this report.

## BGE Readiness

Readiness command:

```powershell
C:\Users\19726\Documents\CrisisAgent\.venv\Scripts\python.exe scripts\check_bge_readiness.py
```

Environment:

```powershell
HF_HOME=C:\Users\19726\Documents\hf-cache
```

Result:

- status: `BGE_READY`
- embedding dimension: `512`
- shape: `[3, 512]`
- dtype: `float32`
- vector norms: `[1.0, 1.0, 1.0]`
- NaN detected: `false`
- Inf detected: `false`
- Hash fallback: `false`
- cold model load observed in this run: `17484.98 ms`
- warm batch embedding: `21.83 ms`
- per-text average embedding: `59.96 ms`

The cold load number is an observed smoke-test load time, not a benchmark or SLA.

## Smoke A: Current Crisis via Dynamic Runtime

Input scenario:

- Chinese food safety crisis: a food brand was exposed for using expired ingredients; related videos were spreading online; consumers requested regulatory intervention.

Entry path:

- Dynamic Runtime
- Agents executed: `sentiment`, `writer`, `redteam`, `legal`, `writer_v2`, `decision`

Result:

- request success: `true`
- failed agents: `[]`
- final output present: `true`
- Legal Agent status: `success`

Retrieval Gate:

- `need_rag`: `true`
- intent: `crisis_response_needed`
- retrieval skipped: `false`

Retrieval:

- retrieval executed: `true`
- retrieval status: `executed_with_hits`
- retrieval fallback used: `false`
- sources: `["food_safety.md"]`
- source count: `1`
- rerank scores: `[0.3804, 0.3687, 0.3683]`

Model behavior:

- DeepSeek was requested by multiple agents.
- Sentiment, Writer, Legal, Writer v2, and Decision completed through the LLM path.
- RedTeam made a real DeepSeek request but fell back to mock because the parsed JSON was missing the required `suggestions` field.
- Legal Agent LLM fallback: `false`
- Overall Dynamic Runtime completed successfully despite RedTeam fallback.

Interpretation:

- DeepSeek client worked for the integrated dynamic path.
- Legal Agent entered the real LLM path.
- Gate v3 allowed RAG for a current crisis.
- BGE retrieval and Reranker v2 participated in the Legal Agent retrieval path.
- Trace separated retrieval fallback from LLM fallback.
- This result must not be described as all agents succeeding through real LLM output, because RedTeam fallback was observed.

## Smoke B: Gate Skip Through Legal Agent Path

Input scenario:

- Chinese non-current training task: summarize personal information protection regulations for internal training; there is currently no active data incident.

Entry path:

- Legal Agent direct run, using the same Legal Agent LLM path.
- Retriever was patched to raise if called, to verify Gate skip happens before retrieval.

Retrieval Gate:

- `need_rag`: `false`
- current incident: `false`
- task intent: `training_learning`
- decision path: `non_current_task_reject`
- reason: no current real-world crisis was detected, and the task was classified as `training_learning`, so RAG was not triggered.

Retrieval:

- retriever call count: `0`
- retrieval skipped: `true`
- retrieval executed: `false`
- retrieval status: `skipped_by_gate`
- retrieval fallback used: `false`
- sources: `[]`
- count: `0`

Model behavior:

- DeepSeek request was sent.
- HTTP status: `200 OK`
- Legal Agent output fell back to mock because the LLM response could not be parsed as JSON.
- Legal LLM fallback used: `true`

Interpretation:

- Gate skip worked correctly and did not call the retriever.
- Gate skip was not counted as retrieval fallback.
- The Legal Agent remained operational through existing mock fallback after LLM JSON parsing failed.
- This smoke exposed LLM structured-output instability, not a Gate/RAG integration failure.

## Smoke C

Smoke C was not executed. The objective was a minimal real-model smoke, and Smoke A plus Smoke B already covered:

- current crisis with RAG execution,
- non-current task with Gate skip,
- DeepSeek HTTP connectivity,
- BGE readiness and retrieval participation,
- LLM fallback distinction.

## Request Count

Official smoke runs made a small number of real DeepSeek calls:

- Smoke A: 6 agent-level LLM requests were attempted in the Dynamic Runtime path.
- Smoke B: 1 Legal Agent LLM request was attempted.
- Total official smoke LLM requests: 7.

One preliminary encoding/config probe was also run before the official smoke cases; its business input was not used as a smoke result because PowerShell literal encoding produced corrupted Chinese text.

## Observed Limitations

1. This is not a reliability benchmark and does not measure repeated-run stability.
2. The system currently has no automatic LLM retry.
3. RedTeam can still fallback when the LLM response misses required JSON fields.
4. Legal Agent can still fallback when DeepSeek returns content that cannot be parsed as JSON.
5. Real DeepSeek output showed structured JSON format instability. The current system keeps the business flow running through JSON parsing, required-field validation, and mock fallback, but it does not implement automatic retry.
6. BGE readiness was verified in the local cached environment only.
7. Smoke C was intentionally skipped to keep real-model calls minimal.
8. `_LAST_RAG_INFO` remains module-level Legal Agent state, so concurrent trace isolation is still a known limitation from earlier regression reports.

## Final Status

Result: `PASS_WITH_LLM_FALLBACK_OBSERVED`

The smoke verifies real DeepSeek connectivity, real BGE readiness, Gate skip behavior, Legal Agent RAG execution, Reranker score propagation, and Dynamic Runtime completion. It also records real LLM fallback behavior rather than treating fallback output as full LLM success. It does not claim production reliability, all-agent LLM success, or automatic retry.
