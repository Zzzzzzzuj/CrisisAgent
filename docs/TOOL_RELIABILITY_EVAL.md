# Tool Reliability Evaluation

## Why this evaluation exists

Tool registration alone does not show that an Agent can recover from real execution problems. This offline evaluation exercises the ToolRunner contract with deterministic fake handlers before any future main-runtime integration.

## Difference from Agent output evaluation

Agent output evaluation asks whether the final result is useful, safe or correct. Tool Reliability Evaluation asks whether the tool layer behaves predictably when a call succeeds, fails, times out, returns invalid output, retries, falls back or repeats the same call.

## Covered cases

The fixed local case file `data/tool_reliability_cases.json` covers:

- basic success and invalid input;
- handler exception and timeout;
- retry success and retry exhaustion;
- invalid output schema;
- fallback success and fallback failure;
- disabled and missing tools;
- repeated tool call and `TOOL_LOOP_DETECTED`.

## Metrics

The evaluator reports:

```text
total_cases
success_cases / failed_cases
tool_success_rate / tool_failure_rate
retry_rate
fallback_rate
timeout_rate
output_validation_failure_rate
loop_detected_rate
human_review_trigger_rate
error_code_counts
```

Rates are calculated from actual `ToolResult` values over the fixed cases. They are reliability observations for this fake-tool suite, not production availability or model quality metrics.

## How to run

```powershell
python scripts/run_tool_reliability_demo.py --pretty
python scripts/run_tool_reliability_demo.py --pretty --output reports/tool_reliability_report.json
```

The demo is offline by construction. It does not call a network, LLM, PostgreSQL, Redis or BGE. It uses fake handlers to make timeout, retry and fallback behavior deterministic.

## Current boundary

This is not a benchmark of DeepSeek, BGE, RAG quality or the full CrisisAgent workflow. It does not prove production SLA, distributed execution or resilience under real provider load. ToolRunner remains a side-path capability and is not connected to the main Executor in this phase.

## Interview version

> I separated tool reliability from final Agent quality evaluation. I built a fixed offline suite with fake handlers for success, invalid input/output, timeout, retry, fallback, disabled tools and repeated calls. The evaluator calculates tool success, retry, fallback, timeout, loop detection and human-review trigger rates from actual ToolResult values. This lets me verify the execution contract without spending real LLM calls or hiding failures behind a successful final answer.
