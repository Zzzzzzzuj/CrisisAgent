import json

from evaluation import embedding_evaluator
from evaluation.embedding_metrics import (
    calculate_case_metrics,
    calculate_case_recall_at_k,
    find_first_target_rank,
    summarize_embedding_results,
)


CASES = [
    {
        "id": "case-food",
        "query": "食品企业使用过期原料",
        "expected_sources": ["food_safety.md"],
        "top_k": 3,
    },
    {
        "id": "case-legal",
        "query": "避免提前定责",
        "expected_sources": ["legal_risk_rules.md"],
        "top_k": 3,
    },
]


def test_embedding_cases_can_be_loaded(tmp_path):
    cases_path = tmp_path / "embedding_cases.json"
    cases_path.write_text(json.dumps(CASES, ensure_ascii=False), encoding="utf-8")

    cases = embedding_evaluator.load_cases(cases_path)

    assert cases == CASES


def test_embedding_metrics_calculate_recall_mrr_and_rank():
    metrics = calculate_case_metrics(
        expected_sources=["legal_risk_rules.md"],
        retrieved_sources=["food_safety.md", "legal_risk_rules.md", "crisis_response.md"],
    )

    assert metrics["recall_at_k"] == 1.0
    assert metrics["reciprocal_rank"] == 0.5
    assert metrics["target_rank"] == 2
    assert calculate_case_recall_at_k(["missing.md"], ["food_safety.md"]) == 0.0
    assert find_first_target_rank(["missing.md"], ["food_safety.md"]) is None


def test_embedding_metrics_summary_calculates_average_target_rank():
    summary = summarize_embedding_results(
        [
            {"recall_at_k": 1.0, "reciprocal_rank": 1.0, "target_rank": 1},
            {"recall_at_k": 0.0, "reciprocal_rank": 0.0, "target_rank": None},
        ]
    )

    assert summary == {
        "total_cases": 2,
        "recall_at_k": 0.5,
        "mrr": 0.5,
        "average_target_rank": 1.0,
    }


def test_embedding_evaluator_hash_mode_runs():
    result = embedding_evaluator.evaluate_model("hash", CASES)

    assert result["model"] == "hash"
    assert result["summary"]["total_cases"] == 2
    assert len(result["case_results"]) == 2
    assert all("retrieved_sources" in item for item in result["case_results"])


def test_embedding_evaluator_bge_mode_runs_with_mock(monkeypatch):
    class FakeBGEEmbeddingModel:
        def embed(self, text):
            if "food" in text.lower() or "食品" in text or "过期" in text:
                return [1.0, 0.0, 0.0]
            if "legal" in text.lower() or "定责" in text or "责任" in text:
                return [0.0, 1.0, 0.0]
            return [0.0, 0.0, 1.0]

    monkeypatch.setattr(embedding_evaluator, "BGEEmbeddingModel", FakeBGEEmbeddingModel)

    result = embedding_evaluator.evaluate_model("bge", CASES)

    assert result["model"] == "bge"
    assert result["summary"]["total_cases"] == 2
    assert len(result["case_results"]) == 2


def test_embedding_evaluator_generates_json_and_markdown_reports(monkeypatch, tmp_path):
    cases_path = tmp_path / "embedding_cases.json"
    cases_path.write_text(json.dumps(CASES, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(
        embedding_evaluator,
        "evaluate_model",
        lambda model, cases: {
            "model": model,
            "summary": {
                "total_cases": len(cases),
                "recall_at_k": 1.0,
                "mrr": 1.0,
                "average_target_rank": 1.0,
            },
            "case_results": [
                {
                    "id": case["id"],
                    "query": case["query"],
                    "expected_sources": case["expected_sources"],
                    "retrieved_sources": case["expected_sources"],
                    "recall_at_k": 1.0,
                    "reciprocal_rank": 1.0,
                    "target_rank": 1,
                }
                for case in cases
            ],
        },
    )

    summary = embedding_evaluator.evaluate_embeddings(cases_path, models=["hash", "bge"])
    saved_paths = embedding_evaluator.save_results(
        summary,
        outputs_dir=tmp_path / "outputs",
        reports_dir=tmp_path / "reports",
    )

    assert summary["total_cases"] == 2
    assert len(summary["models"]) == 2
    assert saved_paths["json_path"].endswith(".json")
    assert saved_paths["markdown_path"].endswith("latest_embedding_report.md")
    assert "Embedding Retrieval Evaluation" in (tmp_path / "reports" / "latest_embedding_report.md").read_text(
        encoding="utf-8"
    )
