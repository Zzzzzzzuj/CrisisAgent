"""Print a deterministic instrumentation baseline from synthetic safe traces."""

from __future__ import annotations

import json
from pathlib import Path

from backend.observability.run_metrics import build_run_metrics


FIXTURE_PATH = Path(__file__).with_name("p5_0_observability_frozen.json")


def build_baseline() -> dict:
    frozen = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    cases = []
    for item in frozen["cases"]:
        case_id = item["case_id"]
        trace = _fixture_trace(case_id)
        metrics = build_run_metrics(case_id, trace, "COMPLETED", {"decision": "approved"})
        cases.append({"case_id": case_id, "expected_observable_events": item["expected_observable_events"],
                      "metrics": metrics})
    return {
        "baseline_version": frozen["version"],
        "data_kind": frozen["data_kind"],
        "performance_interpretation": "instrumentation_only_not_real_workflow_or_provider_performance",
        "mock_latency_is_real_provider_latency": False,
        "mock_tokens_are_provider_tokens": False,
        "mock_cost_is_production_cost": False,
        "token_reduction": "NOT_CLAIMED",
        "cost_reduction": "NOT_CLAIMED",
        "latency_improvement": "NOT_CLAIMED",
        "cases": cases,
        "totals": {
            "agent_executions": sum(sum(a["execution_count"] for a in c["metrics"]["agent_metrics"]) for c in cases),
            "llm_calls": sum(c["metrics"]["llm_call_count"] for c in cases),
            "retrieval_calls": sum(c["metrics"]["retrieval_call_count"] for c in cases),
            "tool_calls": sum(c["metrics"]["tool_call_count"] for c in cases),
            "fallback_cases": [c["case_id"] for c in cases if c["metrics"]["fallback_count"]],
            "human_gate_cases": [c["case_id"] for c in cases if c["metrics"]["human_intervention_count"]],
            "token_source": "estimated_or_unavailable_mock_fixture",
            "cost_estimation_status": "unavailable",
        },
    }


def _fixture_trace(case_id: str) -> list[dict]:
    base = {"agent": "legal", "status": "success", "start_time": "2026-01-01T00:00:00+00:00",
            "end_time": "2026-01-01T00:00:00.010000+00:00", "duration_ms": 10.0}
    if case_id == "O1":
        return [{**base, "agent": "sentiment", "llm_calls": [{"latency_ms": 4.0, "success": True,
                "fallback_used": False, "token_source": "estimated", "estimated_tokens": 12}]}]
    if case_id == "O2":
        return [{**base, "rag": {"retrieval_executed": True, "retrieval_latency_ms": 3.0,
                "retrieval_status": "executed_with_hits"},
                "skills": {"results": [{"success": True, "trace": {"duration_ms": 1.5}}]}}]
    if case_id == "O3":
        return [{"agent": "human_fact", "action": "REQUEST_HUMAN_FACT_VERIFICATION", "status": "success"},
                {"agent": "human_fact", "action": "HUMAN_FACT_RESPONSE", "status": "success"}]
    if case_id == "O4":
        return [{"agent": "human_gate", "status": "waiting_human"},
                {"agent": "human_gate", "status": "approved"}]
    if case_id == "O5":
        return [{**base, "llm_calls": [{"latency_ms": 7.0, "success": False, "fallback_used": True,
                "failure_type": "timeout", "token_source": "unavailable"}]}]
    if case_id == "O6":
        return [{**base, "context_pack": {"chars_before": 1400, "chars_after": 900,
                "budget_chars": 1000, "truncated": True}}]
    raise ValueError(f"Unknown frozen observability case: {case_id}")


if __name__ == "__main__":
    print(json.dumps(build_baseline(), ensure_ascii=False, indent=2))
