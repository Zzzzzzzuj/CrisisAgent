import json
from pathlib import Path

from backend.rag.schemas import RetrievalResult
from scripts.evaluate_rag_retrieval import (
    evaluate_cases,
    load_cases,
    write_reports,
)


class EmptyRetriever:
    def retrieve(self, query: str, top_k: int = 3) -> RetrievalResult:
        return RetrievalResult(context="", chunks=[], sources=[])


def test_rag_retrieval_eval_cases_schema():
    cases = load_cases()

    assert len(cases) >= 8
    required = {
        "case_id",
        "crisis_event",
        "expected_source_category",
        "expected_keywords",
        "expected_document_hint",
        "difficulty",
        "notes",
    }
    assert all(required <= set(case) for case in cases)
    assert {case["difficulty"] for case in cases} <= {"easy", "medium", "hard"}
    assert len({case["case_id"] for case in cases}) == len(cases)
    assert {
        "food_safety",
        "data_privacy",
        "service_outage",
        "false_advertising",
        "labor_dispute",
        "product_recall",
        "financial_rumor",
        "executive_scandal",
    } <= {case["expected_source_category"] for case in cases}


def test_evaluate_cases_reports_empty_knowledge_base_hint():
    cases = [
        {
            "case_id": "empty",
            "crisis_event": "无检索结果测试",
            "expected_source_category": "food_safety",
            "expected_keywords": ["食品"],
            "expected_document_hint": "food_safety.md",
            "difficulty": "easy",
            "notes": "",
        }
    ]

    result = evaluate_cases(cases, retriever=EmptyRetriever())

    assert result["summary"]["total_cases"] == 1
    assert result["summary"]["top3_source_hit_rate"] == 0.0
    assert "No RAG chunks were returned" in result["empty_knowledge_base_hint"]


def test_write_reports_generates_json_and_markdown(tmp_path):
    result = {
        "summary": {
            "total_cases": 1,
            "top1_source_hit_rate": 1.0,
            "top3_source_hit_rate": 1.0,
            "keyword_hit_rate": 1.0,
            "fallback_rate": 0.0,
            "average_score": 0.8,
            "average_rerank_score": 0.7,
            "backend_distribution": {"markdown": 1},
            "failed_cases": [],
        },
        "cases": [
            {
                "case_id": "case-1",
                "difficulty": "easy",
                "expected_source_category": "food_safety",
                "actual_source_categories": ["food_safety"],
                "top1_source_hit": True,
                "top3_source_hit": True,
                "keyword_hits": ["食品"],
                "fallback_used": False,
                "failure_reason": "",
                "top_chunks": [
                    {
                        "source": "food_safety.md",
                        "source_category": "food_safety",
                        "score": 0.8,
                        "rerank_score": 0.7,
                        "retrieval_backend": "markdown",
                        "text_preview": "食品安全核查。",
                    }
                ],
            }
        ],
        "empty_knowledge_base_hint": "",
    }
    json_path = tmp_path / "report.json"
    markdown_path = tmp_path / "report.md"

    write_reports(result, json_path=json_path, markdown_path=markdown_path)

    assert json.loads(json_path.read_text(encoding="utf-8"))["summary"]["total_cases"] == 1
    assert "# RAG Retrieval Evaluation Report" in markdown_path.read_text(encoding="utf-8")
