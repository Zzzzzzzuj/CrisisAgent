import json
from pathlib import Path

from evaluation import evaluator


def test_load_cases_reads_rag_fields(tmp_path: Path):
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(
        json.dumps(
            [
                {
                    "id": "case-1",
                    "event": "event A",
                    "expected_risk": "high",
                    "expected_emotion": "angry",
                    "expected_tone": "tone A",
                    "category": "food_safety",
                    "tags": ["tag-1", "tag-2"],
                    "expected_sources": ["food_safety.md"],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    cases = evaluator.load_cases(cases_path)

    assert len(cases) == 1
    assert cases[0]["category"] == "food_safety"
    assert cases[0]["expected_tone"] == "tone A"
    assert cases[0]["tags"] == ["tag-1", "tag-2"]
    assert cases[0]["expected_sources"] == ["food_safety.md"]


def test_summarize_results_includes_rag_and_category_metrics():
    summary = evaluator.summarize_results(
        [
            {
                "id": "case-1",
                "category": "food_safety",
                "risk_match": True,
                "emotion_match": False,
                "tone_match": True,
                "trace_duration_ms": 100,
                "fallback": True,
                "rag_enabled": True,
                "rag_hit": True,
                "rag_sources": ["food_safety.md"],
                "rag_source_count": 1,
                "expected_sources": ["food_safety.md"],
                "recall_at_k": 1.0,
                "reciprocal_rank": 1.0,
                "rerank_gain": 1,
                "trace": [
                    {
                        "agent": "Agent A",
                        "name": "sentiment",
                        "start_time": "2026-07-20T10:00:00+00:00",
                        "end_time": "2026-07-20T10:00:01+00:00",
                        "fallback": False,
                    }
                ],
            },
            {
                "id": "case-2",
                "category": "food_safety",
                "risk_match": False,
                "emotion_match": True,
                "tone_match": False,
                "trace_duration_ms": 300,
                "fallback": False,
                "rag_enabled": True,
                "rag_hit": False,
                "rag_sources": [],
                "rag_source_count": 0,
                "expected_sources": ["food_safety.md"],
                "recall_at_k": 0.0,
                "reciprocal_rank": 0.0,
                "rerank_gain": 0,
                "trace": [
                    {
                        "agent": "Agent A",
                        "name": "sentiment",
                        "start_time": "2026-07-20T10:01:00+00:00",
                        "end_time": "2026-07-20T10:01:02+00:00",
                        "fallback": False,
                    }
                ],
            },
        ]
    )

    assert summary["total_cases"] == 2
    assert summary["risk_accuracy"] == 0.5
    assert summary["emotion_accuracy"] == 0.5
    assert summary["tone_accuracy"] == 0.5
    assert summary["rag_hit_rate"] == 0.5
    assert summary["recall_at_k"] == 0.5
    assert summary["mrr"] == 0.5
    assert summary["average_rerank_gain"] == 0.5
    assert summary["average_retrieved_sources"] == 0.5
    assert summary["source_distribution"] == {"food_safety.md": 1}
    assert summary["category_metrics"]["food_safety"]["total_cases"] == 2
    assert summary["category_metrics"]["food_safety"]["risk_accuracy"] == 0.5
    assert summary["category_metrics"]["food_safety"]["tone_accuracy"] == 0.5
    assert summary["category_metrics"]["food_safety"]["rag_hit_rate"] == 0.5


def test_evaluate_case_collects_rag_trace_fields(monkeypatch):
    fake_response = {
        "session_id": "session-1",
        "final_statement": "statement",
        "scores": {"legal_safety": 8, "empathy": 7, "robustness": 9},
        "agent_trace": [
            {
                "agent": "Agent A",
                "name": "sentiment",
                "input": "event A",
                "output": {
                    "risk_level": "high",
                    "public_emotion": "angry",
                    "keywords": ["exposure"],
                    "recommended_tone": "tone A",
                    "analysis_summary": "summary",
                },
                "start_time": "2026-07-20T10:00:00+00:00",
                "end_time": "2026-07-20T10:00:01+00:00",
                "status": "success",
                "mode": "mock",
                "fallback": False,
                "rag": None,
            },
            {
                "agent": "Agent B",
                "name": "legal",
                "input": {},
                "output": {},
                "start_time": "2026-07-20T10:00:01+00:00",
                "end_time": "2026-07-20T10:00:02+00:00",
                "status": "success",
                "mode": "llm",
                "fallback": False,
                "rag": {
                    "enabled": True,
                    "hit": True,
                    "retrieval_type": "hybrid",
                    "rerank_enabled": True,
                    "query": "event A legal query",
                    "sources": ["food_safety.md", "legal_risk_rules.md"],
                    "chunks": [
                        {
                            "chunk_id": "legal-1",
                            "source": "legal_risk_rules.md",
                            "title": "Legal",
                            "score": 0.9,
                            "rerank_score": 0.8,
                            "text_preview": "avoid premature liability",
                        },
                        {
                            "chunk_id": "food-1",
                            "source": "food_safety.md",
                            "title": "Food",
                            "score": 0.7,
                            "rerank_score": 0.95,
                            "text_preview": "food safety",
                        },
                    ],
                    "scores": [0.9, 0.7],
                    "rerank_scores": [0.8, 0.95],
                    "count": 2,
                },
            },
        ],
    }

    class FakeResult:
        def model_dump(self):
            return fake_response

    monkeypatch.setattr(evaluator, "run_crisis_workflow", lambda request: FakeResult())

    result = evaluator.evaluate_case(
        {
            "id": "case-1",
            "event": "event A",
            "expected_risk": "high",
            "expected_emotion": "angry",
            "expected_tone": "tone A",
            "category": "food_safety",
            "tags": ["tag-1"],
            "expected_sources": ["food_safety.md"],
        }
    )

    assert result["category"] == "food_safety"
    assert result["tags"] == ["tag-1"]
    assert result["predicted_tone"] == "tone A"
    assert result["tone_match"] is True
    assert result["final_scores"] == {"legal_safety": 8, "empathy": 7, "robustness": 9}
    assert result["expected_sources"] == ["food_safety.md"]
    assert result["rag_enabled"] is True
    assert result["rag_hit"] is True
    assert result["rag_sources"] == ["food_safety.md", "legal_risk_rules.md"]
    assert result["rag_source_count"] == 2
    assert result["rag_retrieval_type"] == "hybrid"
    assert result["rag_query"] == "event A legal query"
    assert result["rerank_enabled"] is True
    assert result["recall_at_k"] == 1.0
    assert result["reciprocal_rank"] == 1.0
    assert result["before_rank"] == 2
    assert result["after_rank"] == 1
    assert result["rerank_gain"] == 1


def test_save_results_generates_json_and_markdown_reports_with_rag(tmp_path: Path):
    summary = {
        "total_cases": 1,
        "risk_accuracy": 1.0,
        "emotion_accuracy": 1.0,
        "tone_accuracy": 1.0,
        "fallback_rate": 0.0,
        "average_duration_ms": 120.0,
        "rag_hit_rate": 1.0,
        "recall_at_k": 1.0,
        "mrr": 1.0,
        "average_rerank_gain": 1.0,
        "average_retrieved_sources": 1.0,
        "source_distribution": {"food_safety.md": 1},
        "agent_metrics": {
            "Agent A": {
                "agent": "Agent A",
                "name": "sentiment",
                "average_duration_ms": 50.0,
                "fallback_count": 0,
                "fallback_rate": 0.0,
                "total_runs": 1,
            }
        },
        "category_metrics": {
            "food_safety": {
                "total_cases": 1,
                "risk_accuracy": 1.0,
                "emotion_accuracy": 1.0,
                "tone_accuracy": 1.0,
                "fallback_rate": 0.0,
                "average_duration_ms": 120.0,
                "rag_hit_rate": 1.0,
                "recall_at_k": 1.0,
                "mrr": 1.0,
                "average_rerank_gain": 1.0,
                "average_retrieved_sources": 1.0,
            }
        },
        "case_results": [
            {
                "id": "case-1",
                "event": "event A",
                "category": "food_safety",
                "tags": ["tag-1"],
                "expected_risk": "high",
                "expected_emotion": "angry",
                "expected_tone": "tone A",
                "expected_sources": ["food_safety.md"],
                "predicted_risk": "high",
                "predicted_emotion": "angry",
                "predicted_tone": "tone A",
                "risk_match": True,
                "emotion_match": True,
                "tone_match": True,
                "agent_a_output": {"risk_level": "high"},
                "final_scores": {"legal_safety": 8, "empathy": 7, "robustness": 9},
                "trace": [],
                "trace_duration_ms": 120,
                "fallback_count": 0,
                "fallback": False,
                "rag_enabled": True,
                "rag_hit": True,
                "rag_sources": ["food_safety.md"],
                "rag_source_count": 1,
                "rag_retrieval_type": "hybrid",
                "rag_query": "event A legal query",
                "rag_chunks": [],
                "rag_scores": [0.8],
                "rag_rerank_scores": [0.9],
                "rerank_enabled": True,
                "recall_at_k": 1.0,
                "reciprocal_rank": 1.0,
                "before_rank": 1,
                "after_rank": 1,
                "rerank_gain": 0,
            }
        ],
    }

    saved_paths = evaluator.save_results(
        summary,
        outputs_dir=tmp_path / "outputs",
        reports_dir=tmp_path / "reports",
    )

    json_path = Path(saved_paths["json_path"])
    markdown_path = Path(saved_paths["markdown_path"])

    assert json_path.exists()
    assert markdown_path.exists()

    saved_json = json.loads(json_path.read_text(encoding="utf-8"))
    saved_markdown = markdown_path.read_text(encoding="utf-8")

    assert saved_json["tone_accuracy"] == 1.0
    assert saved_json["rag_hit_rate"] == 1.0
    assert saved_json["recall_at_k"] == 1.0
    assert "## RAG Evaluation" in saved_markdown
    assert "Recall@K" in saved_markdown
    assert "MRR" in saved_markdown
    assert "## RAG Source Distribution" in saved_markdown
    assert "## Category Metrics" in saved_markdown
    assert "food_safety" in saved_markdown
    assert "PASS" in saved_markdown
