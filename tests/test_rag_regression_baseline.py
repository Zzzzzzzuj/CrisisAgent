import json

from backend.rag.schemas import RetrievalResult, RetrievedChunk
from scripts.run_rag_regression import (
    compare_to_baseline,
    load_baseline,
    run_regression,
    write_reports,
)


class StubRetriever:
    def __init__(self, source_category: str = "food_safety") -> None:
        self.source_category = source_category

    def retrieve(self, query: str, top_k: int = 3) -> RetrievalResult:
        return RetrievalResult(
            context="食品安全证据。监管核查整改。",
            chunks=[
                RetrievedChunk(
                    text="食品安全证据。监管核查整改。",
                    source="food_safety.md",
                    title="食品安全",
                    score=0.8,
                    rerank_score=0.7,
                    chunk_id="chunk-1",
                    metadata={
                        "source_category": self.source_category,
                        "retrieval_backend": "markdown",
                        "retrieval_fallback": False,
                    },
                )
            ],
            sources=[],
        )


def _case(expected_category: str = "food_safety") -> dict:
    return {
        "case_id": "case-1",
        "event": "某食品品牌出现安全争议，需要核查监管沟通。",
        "crisis_event": "某食品品牌出现安全争议，需要核查监管沟通。",
        "expected_need_retrieval": True,
        "expected_source_category": expected_category,
        "expected_keywords": ["食品", "监管"],
        "expected_human_review": True,
        "expected_document_hint": "food_safety.md",
        "difficulty": "easy",
        "notes": "",
    }


def test_baseline_file_can_be_read():
    baseline = load_baseline()

    assert baseline is not None
    assert baseline["total_cases"] >= 8
    assert "top3_source_hit_rate" in baseline
    assert "context_pollution_rate" in baseline


def test_regression_runs_offline_with_stub_retriever():
    result = run_regression(
        cases=[_case()],
        baseline={
            "top3_source_hit_rate": 1.0,
            "fallback_rate": 0.0,
            "context_pollution_rate": 0.0,
        },
        retriever=StubRetriever(),
    )

    assert result["summary"]["baseline_available"] is True
    assert result["summary"]["regression_passed"] is True
    assert result["current_metrics"]["top3_source_hit_rate"] == 1.0


def test_regression_marks_failed_when_metric_degrades_beyond_threshold():
    comparison = compare_to_baseline(
        current={
            "top3_source_hit_rate": 0.6,
            "fallback_rate": 0.25,
            "context_pollution_rate": 0.5,
        },
        baseline={
            "top3_source_hit_rate": 0.8,
            "fallback_rate": 0.0,
            "context_pollution_rate": 0.2,
        },
    )

    assert comparison["passed"] is False
    assert {check["metric"] for check in comparison["checks"] if check["status"] == "failed"} == {
        "top3_source_hit_rate",
        "fallback_rate",
        "context_pollution_rate",
    }


def test_regression_passes_when_metrics_do_not_degrade_beyond_threshold():
    comparison = compare_to_baseline(
        current={
            "top3_source_hit_rate": 0.72,
            "fallback_rate": 0.05,
            "context_pollution_rate": 0.31,
        },
        baseline={
            "top3_source_hit_rate": 0.8,
            "fallback_rate": 0.0,
            "context_pollution_rate": 0.2,
        },
    )

    assert comparison["passed"] is True


def test_missing_baseline_does_not_crash_and_generates_current_report():
    result = run_regression(cases=[_case()], baseline=None, retriever=StubRetriever())

    assert result["summary"]["baseline_available"] is False
    assert result["summary"]["regression_passed"] is True
    assert result["summary"]["checks"][0]["reason"] == "baseline_not_found"
    assert result["current_metrics"]["total_cases"] == 1


def test_report_contains_failed_cases_and_summary(tmp_path):
    result = run_regression(
        cases=[_case(expected_category="data_privacy")],
        baseline=None,
        retriever=StubRetriever(source_category="food_safety"),
    )
    json_path = tmp_path / "rag_regression_report.json"
    markdown_path = tmp_path / "rag_regression_report.md"

    write_reports(result, json_path=json_path, markdown_path=markdown_path)

    parsed = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "summary" in parsed
    assert "failed_cases" in parsed
    assert parsed["failed_cases"][0]["possible_causes"]
    assert "## Failed Cases" in markdown
