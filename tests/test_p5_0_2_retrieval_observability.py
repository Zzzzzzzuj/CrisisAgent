import json
from unittest.mock import patch

from backend.rag.document_loader import KNOWLEDGE_BASE_DIR
from backend.rag.pipeline_retriever import RagPipelineRetriever
from evaluation.p5_0_mock_workflow_baseline import (
    FIXTURE_PATH, _run_local_legal_retrieval, build_baseline,
)


def test_m4_uses_workflow_and_local_retriever_without_exposing_content(monkeypatch):
    assert "不得在生产经营中使用超过保质期的食品原料" in (
        KNOWLEDGE_BASE_DIR / "food_safety.md").read_text(encoding="utf-8")
    original_retrieve = RagPipelineRetriever.retrieve
    pipeline_calls = []

    def recording_retrieve(self, query, top_k=3):
        pipeline_calls.append(top_k)
        return original_retrieve(self, query, top_k=top_k)

    monkeypatch.setattr(RagPipelineRetriever, "retrieve", recording_retrieve)
    with patch("httpx.Client.post", side_effect=AssertionError("external request blocked")) as post:
        baseline = build_baseline()
    assert post.call_count == 0
    m4 = baseline["cases"][3]
    metrics = m4["metrics"]

    assert m4["case_id"] == "M4"
    assert "legal" in m4["executed_agents"]
    assert pipeline_calls
    assert metrics["retrieval_call_count"] == len(m4["retrieval_trace"]) >= 1
    assert metrics["retrieval_latency_ms"] is not None
    assert metrics["retrieval_latency_ms"] >= 0
    assert m4["retrieval_latency_available"] is True
    assert m4["retrieval_status"] in {"SUCCESS", "NO_HIT", "FALLBACK", "ERROR"}
    assert set(m4["retrieval_trace"][0]) == {"status", "latency_ms"}

    serialized = repr(m4["retrieval_trace"])
    for forbidden in ("不得在生产经营中使用超过保质期", "某食品品牌", "Authorization", "Bearer", "prompt", "query"):
        assert forbidden not in serialized


def test_m4_workflow_survives_metrics_failure(monkeypatch):
    def fail_metrics(*args, **kwargs):
        raise RuntimeError("metrics unavailable")

    monkeypatch.setattr("backend.observability.run_metrics.build_run_metrics", fail_metrics)
    monkeypatch.setattr("backend.core.dynamic_runtime.build_run_metrics", fail_metrics)
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    event = next(case["event"] for case in fixture["cases"] if case["case_id"] == "M4")
    result = _run_local_legal_retrieval(event)

    assert "legal" in result["executed_agents"]
    assert result["results"]["legal"]
    assert result["run_metrics"] is None
    legal_trace = next(row for row in result["execution_trace"] if row.get("agent") == "legal")
    assert legal_trace.get("retrieval_calls")
    serialized = json.dumps(legal_trace, ensure_ascii=False)
    for forbidden in (event, "企业不得在生产经营中使用超过保质期的食品原料",
                      "待审核声明 draft", "检索到的合规知识", "Authorization", "Bearer"):
        assert forbidden not in serialized
