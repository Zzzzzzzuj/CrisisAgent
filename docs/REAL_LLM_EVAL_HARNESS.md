# Real LLM Evaluation Harness Reliability

## Scope

This evaluation-only harness persists one allowlisted, content-minimized result per case. The reusable runner is `scripts/run_real_llm_semantic_validation.py`; it supports the default frozen five-case slice and explicit `--case-id` selection through the real `/api/dynamic/run` and, when the session is at `FACT_INPUT`, `/api/dynamic/{session_id}/fact-response` API routes. It does not change Agent behavior. Default `--mode fake` forces Mock + `OFFLINE_EVAL=1` and blocks outbound requests. `--mode real` requires both `--confirm-real-provider` and a DeepSeek-compatible config.

The runner validates the frozen dataset identity before creating a run. Without `--case-id`, it uses the unchanged default slice `privacy-03`, `food-03`, `outage-01`, `complaint-02`, `outage-02`. Explicit case selection loads from the same frozen dataset. Bounded multi-`FACT_INPUT` evaluation supports `single_frozen_response` and `repeat_frozen_unavailable`; the latter is an evaluation intervention that repeats a frozen unavailable response, not a re-interpretation of frozen ground truth.

Run the CLI from the repository root. Direct script invocation is supported without setting `PYTHONPATH` or installing the repository as an editable package:

```powershell
python scripts/run_real_llm_semantic_validation.py --help
python scripts/run_real_llm_semantic_validation.py --mode fake
```

Each run gets a unique ID and three independent artifacts under the caller-selected report directory: a JSONL file, a metadata JSON file, and a summary JSON file. The metadata and JSONL are created exclusively, so an existing run is never overwritten. Each case line is appended, flushed, and `fsync`'d before the next case starts. A process crash can therefore lose at most the in-flight case; prior complete records remain readable. A caught case exception is recorded as `status=ERROR` with a safe error type/stage/code and the runner follows its explicit continue-on-error setting.

The summary is deterministically rebuilt from JSONL. It does not depend on terminal output or temporary runtime/checkpoint files. Missing provider token usage is recorded as `null` with `usage_available=false`; no token estimate is substituted.

Only fixed ground-truth labels and a fixed set of diagnostic fields are persisted. Unknown keys, event/claim/evidence/statement text, prompts, authorization values, and exception messages are dropped. Run metadata uses a fixed allowlist and excludes API keys.

## Previous Real-Model Run: Incomplete Capture

This section describes the historical five-case exploratory run, not the latest Real Provider validation.

The prior five-case DeepSeek Semantic Validation must be treated as `INCOMPLETE_CAPTURE`, not as a successful evaluation. Its output was truncated by terminal capture and its temporary report directory was removed after process exit. The available observations are limited to:

- `privacy-03` triggered Human Fact; its frozen `FACT_PROVIDED` response was accepted with HTTP 200.
- `food-03` produced local Legal RAG activity.
- Legal Claim Extraction had a timeout and used fallback.
- RedTeam output missed the required `suggestions` field and used fallback.

The selected five-case list and complete per-case records are not recoverable from the retained artifacts. Do not infer missing cases or metrics. It is not possible to reconstruct TP/FN/FP, all final states, trace-safety results, exact provider-call counts, token usage, or latency distributions. The run does not prove that DeepSeek outperforms Mock, nor that Legal targeted retrieval completed end-to-end.

## Latest food-01 Trigger Replay

One Real Provider Trigger Replay used `deepseek-v4-flash` on `food-01`. The persisted run showed this bounded continuation:

```text
Claim 0 -> FACT_UNAVAILABLE -> Observation -> Claim 1
Claim 1 -> FACT_UNAVAILABLE -> Observation -> Claim 2
Claim 2 -> FACT_UNAVAILABLE -> bounded stop -> Final Review
```

This run did not reproduce the earlier stop-after-first-Claim blocker and is evidence of real-provider bounded multi-Claim continuation in that run. It does not prove Capability B, a proposal changing the deterministic baseline, General ReAct, comprehensive Claim Extraction semantic correctness, or benchmark quality. The earlier run's Claim Extraction provider call timed out and used fallback; the newer run's provider call and structured parsing succeeded. This was not a controlled A/B, so output differences cannot all be attributed to Legal V3.

## Validation

The harness tests use fake callbacks only. They verify incremental persistence, simulated process interruption, structured case errors, summary reconstruction, content exclusion, missing usage handling, independence from runtime cleanup/stdout capture, and unique run IDs. They do not perform real LLM or network calls.

## Windows Runtime Socket Boundary

On Windows, a synchronous Starlette `TestClient` call starts a temporary AnyIO blocking portal. Initializing its Proactor event loop creates an asyncio self-pipe through `socket.socketpair()`, which internally uses a loopback TCP connection. The Real Eval guard permits only that exact runtime call site, only inside the corresponding single API-call portal bootstrap window, with a one-connect budget. The capability is consumed and sealed as soon as the self-pipe connect succeeds. It is not a loopback address/port allowlist and does not authorize application sockets.

Provider requests remain governed independently by the existing logical destination plus direct-transport/configured-proxy policy. The internal capability is unavailable while a logical provider request context is active; it does not authorize `example.com`, unknown hosts, arbitrary localhost services, or public network access. Fake mode remains offline.
