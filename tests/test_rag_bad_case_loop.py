import json

from scripts.analyze_rag_bad_cases import analyze_bad_cases, load_bad_cases, write_report
from scripts.run_knowledge_ingestion_regression import run_regression


ALLOWED_FAILURE_TYPES = {
    "no_retrieval",
    "wrong_source",
    "low_score",
    "stale_document",
    "disabled_document_hit",
    "rerank_misorder",
    "insufficient_evidence",
    "fallback_only",
}

ALLOWED_ROOT_CAUSES = {
    "query_rewrite",
    "knowledge_gap",
    "chunking_issue",
    "embedding_issue",
    "reranker_issue",
    "metadata_filter_issue",
}


def test_rag_bad_cases_schema_and_phase14_links():
    cases = load_bad_cases()

    required = {
        "bad_case_id",
        "crisis_event",
        "query",
        "expected_source_category",
        "actual_source_category",
        "failure_type",
        "root_cause",
        "suggested_fix",
        "status",
        "linked_test_case",
    }
    assert len(cases) >= 8
    assert all(required <= set(case) for case in cases)
    assert len({case["bad_case_id"] for case in cases}) == len(cases)
    assert {case["failure_type"] for case in cases} <= ALLOWED_FAILURE_TYPES
    assert {case["root_cause"] for case in cases} <= ALLOWED_ROOT_CAUSES
    assert {case["status"] for case in cases} <= {"open", "fixed", "wont_fix"}
    assert "rag_eval_false_advertising_001" in {case["linked_test_case"] for case in cases}
    assert "rag_eval_labor_dispute_001" in {case["linked_test_case"] for case in cases}
    assert "rag_eval_financial_rumor_001" in {case["linked_test_case"] for case in cases}


def test_bad_case_analysis_groups_failures_and_writes_report(tmp_path):
    cases = [
        {
            "bad_case_id": "bad-1",
            "crisis_event": "广告宣传被质疑。",
            "query": "广告宣传证明材料。",
            "expected_source_category": "false_advertising",
            "actual_source_category": "crisis_response",
            "failure_type": "wrong_source",
            "root_cause": "knowledge_gap",
            "suggested_fix": "新增 false_advertising 知识文档。",
            "status": "open",
            "linked_test_case": "rag_eval_false_advertising_001",
        },
        {
            "bad_case_id": "bad-2",
            "crisis_event": "disabled 文档不应命中。",
            "query": "禁用文档验证。",
            "expected_source_category": "food_safety",
            "actual_source_category": "food_safety",
            "failure_type": "disabled_document_hit",
            "root_cause": "metadata_filter_issue",
            "suggested_fix": "验证 disabled 过滤。",
            "status": "fixed",
            "linked_test_case": "test_disabled_document_is_not_loaded_for_rag",
        },
    ]
    report_path = tmp_path / "bad_cases.md"

    analysis = analyze_bad_cases(cases)
    write_report(analysis, report_path)

    assert analysis["total_bad_cases"] == 2
    assert analysis["by_failure_type"]["wrong_source"] == 1
    assert analysis["by_root_cause"]["knowledge_gap"] == 1
    assert analysis["by_status"]["open"] == 1
    assert analysis["suggested_knowledge_updates"][0]["source_category"] == "false_advertising"
    report = report_path.read_text(encoding="utf-8")
    assert "# RAG Bad Cases Report" in report
    assert "bad-1" in report


def test_knowledge_ingestion_regression_runs_offline_without_pgvector():
    result = run_regression()

    assert result["status"] == "pass"
    assert all(result["checks"].values())
    assert result["retrievable_chunk_count"] >= 1
    assert result["vector_backend"] in {"json", "pgvector"}
    assert "pgvector" in result["pgvector_note"]
    assert json.dumps(result, ensure_ascii=False)
