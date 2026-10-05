"""Run safe, deterministic mock cases through the existing CrisisAgent workflow."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


FIXTURE_PATH = Path(__file__).with_name("p5_0_mock_workflow_frozen.json")
_SAFETY_ENV = ("AGENT_MODE", "OFFLINE_EVAL", "LLM_API_KEY", "RAG_ENABLED")


class _EmptyHarnessRepository:
    def list_specs(self):
        return []


class _EmptyCaseMemoryStore:
    def list_memories(self, **kwargs):
        return []


def build_baseline() -> dict:
    previous = {key: os.environ.get(key) for key in _SAFETY_ENV}
    os.environ.update({"AGENT_MODE": "mock", "OFFLINE_EVAL": "1", "LLM_API_KEY": "", "RAG_ENABLED": "false"})
    try:
        from backend.config import get_config
        from backend.llm.config import get_llm_config
        from backend.llm.offline_guard import assert_offline_eval_startup

        get_config.cache_clear()
        get_llm_config.cache_clear()
        assert_offline_eval_startup()

        from backend.core.dynamic_runtime import run_dynamic_agent

        frozen = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cases = []
        with patch("backend.harness.service.get_harness_repository", return_value=_EmptyHarnessRepository()), \
                patch("backend.core.context_pack_runtime.get_case_memory_store",
                      return_value=_EmptyCaseMemoryStore()):
            for item in frozen["cases"]:
                result = (_run_local_legal_retrieval(item["event"])
                          if item["case_id"] == "M4" else run_dynamic_agent(item["event"]))
                metrics = result.get("run_metrics")
                if not isinstance(metrics, dict):
                    raise RuntimeError("Workflow did not produce run metrics.")
                legal_trace = next((row for row in result.get("execution_trace", [])
                                    if row.get("agent") == "legal"), {})
                retrieval_trace = [
                    {key: call[key] for key in ("status", "latency_ms") if key in call}
                    for call in legal_trace.get("retrieval_calls", []) if isinstance(call, dict)
                ]
                statuses = metrics["retrieval_status_counts"]
                cases.append({
                    "case_id": item["case_id"],
                    "scenario": item["scenario"],
                    "expected_observable_events": item["expected_observable_events"],
                    "runtime_state": result.get("state_status"),
                    "executed_agents": list(result.get("executed_agents", [])),
                    "metrics": metrics,
                    "retrieval_trace": retrieval_trace,
                    "retrieval_status": next(iter(statuses)) if len(statuses) == 1 else None,
                    "retrieval_latency_available": metrics["retrieval_latency_status"] == "available",
                    "performance_representative": False,
                })

        return {
            "baseline_version": frozen["version"],
            "data_kind": frozen["data_kind"],
            "measurement_source": "run_dynamic_agent_default_registry_and_executor",
            "performance_representative": False,
            "interpretation": "mock_workflow_instrumentation_validation_only",
            "real_provider_performance_baseline": False,
            "mock_latency_is_real_provider_latency": False,
            "mock_tokens_are_provider_tokens": False,
            "mock_cost_is_production_cost": False,
            "retrieval_note": "M1-M3 use mock Legal without RAG; M4 uses deterministic Legal model replies and the existing local RAG pipeline.",
            "cases": cases,
            "totals": {
                "agent_executions": sum(
                    sum(row["execution_count"] for row in case["metrics"]["agent_metrics"])
                    for case in cases
                ),
                "llm_calls": sum(case["metrics"]["llm_call_count"] for case in cases),
                "retrieval_calls": sum(case["metrics"]["retrieval_call_count"] for case in cases),
                "tool_calls": sum(case["metrics"]["tool_call_count"] for case in cases),
                "fallback_count": sum(case["metrics"]["fallback_count"] for case in cases),
                "human_fact_requests": sum(case["metrics"]["human_fact_request_count"] for case in cases),
                "final_reviews": sum(case["metrics"]["final_review_count"] for case in cases),
                "context_chars_before": sum(case["metrics"]["context_chars_before"] for case in cases),
                "context_chars_after": sum(case["metrics"]["context_chars_after"] for case in cases),
                "token_source": _combined_token_source(cases),
                "cost_estimation_status": "unavailable",
            },
            "token_reduction": "NOT_CLAIMED",
            "cost_reduction": "NOT_CLAIMED",
            "latency_improvement": "NOT_CLAIMED",
        }
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if "get_config" in locals():
            get_config.cache_clear()
        if "get_llm_config" in locals():
            get_llm_config.cache_clear()


def _combined_token_source(cases: list[dict]) -> str:
    sources = {case["metrics"].get("token_source", "unavailable") for case in cases}
    return next(iter(sources)) if len(sources) == 1 else "mixed"


def _run_local_legal_retrieval(event: str) -> dict:
    from backend.agents import legal_agent
    from backend.config import get_config
    from backend.core.dynamic_runtime import run_dynamic_agent
    from backend.llm.config import get_llm_config

    def offline_legal_reply(prompt: str) -> str:
        if prompt.startswith("从原始事件和声明草稿中识别"):
            return json.dumps({"claims": []})
        return json.dumps({
            "legal_risks": [], "safe_points": [], "revision_advice": [],
            "public_opinion_suggestions": [], "integrated_revision_tasks": [],
        })

    with patch.dict(os.environ, {"AGENT_MODE": "mock", "OFFLINE_EVAL": "1", "LLM_API_KEY": "",
                                   "RAG_ENABLED": "true", "EMBEDDING_MODEL": "hash",
                                   "VECTOR_BACKEND": "json"}), \
            patch.object(legal_agent, "get_config", return_value=SimpleNamespace(agent_mode="llm")), \
            patch.object(legal_agent, "call_llm", side_effect=offline_legal_reply), \
            patch("backend.harness.service.get_harness_repository", return_value=_EmptyHarnessRepository()), \
            patch("backend.core.context_pack_runtime.get_case_memory_store",
                  return_value=_EmptyCaseMemoryStore()), \
            patch("backend.rag.document_loader._load_database_documents_if_available", return_value=[]), \
            patch("backend.rag.document_loader._load_database_chunks_if_available", return_value=[]):
        get_config.cache_clear()
        get_llm_config.cache_clear()
        try:
            return run_dynamic_agent(event)
        finally:
            get_config.cache_clear()
            get_llm_config.cache_clear()


if __name__ == "__main__":
    print(json.dumps(build_baseline(), ensure_ascii=False, indent=2))
