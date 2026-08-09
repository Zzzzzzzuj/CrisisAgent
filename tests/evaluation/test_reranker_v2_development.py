from evaluation.reranker_v2_development import (
    CANONICAL_CHALLENGE_V3_METRICS,
    DEVELOPMENT_SELECTION_RULE,
    EVALUATION_SCOPE,
    METRIC_DEFINITIONS,
    build_markdown_report,
    compare_variants,
    count_confusion_pairs,
    count_wrong_by_rank,
    metric_differences,
)


def _case(case_id, category, acceptable_sources, retrieved_sources, recall_at_3=1.0):
    return {
        "id": case_id,
        "category": category,
        "acceptable_sources": acceptable_sources,
        "metrics": {
            "retrieved_sources": retrieved_sources,
            "recall_at_3": recall_at_3,
            "context_pollution_rate": 0.0,
        },
    }


def test_count_wrong_by_rank_uses_source_level_order():
    cases = [
        _case("case-1", "data_privacy", ["data_privacy.md"], ["data_privacy.md", "service_outage.md"]),
        _case("case-2", "food_safety", ["food_safety.md"], ["product_quality.md", "food_safety.md"]),
    ]

    counts = count_wrong_by_rank(cases)

    assert counts["rank1"] == 1
    assert counts["rank2"] == 1
    assert counts["rank3"] == 0


def test_count_confusion_pairs_groups_wrong_sources_by_case_category():
    cases = [
        _case("case-1", "data_privacy", ["data_privacy.md"], ["service_outage.md"]),
        _case("case-2", "food_safety", ["food_safety.md"], ["product_quality.md"]),
    ]

    pairs = count_confusion_pairs(cases)

    assert pairs["data_privacy->service_outage"] == 1
    assert pairs["food_safety->product_quality"] == 1


def test_metric_differences_include_core_development_metrics():
    baseline = {
        "recall_at_3": 0.95,
        "source_category_match": 0.4933,
        "context_pollution_rate": 0.3733,
        "pollution_case_count": 17,
    }
    candidate = {
        "recall_at_3": 1.0,
        "source_category_match": 0.5555,
        "context_pollution_rate": 0.2222,
        "pollution_case_count": 8,
    }

    diff = metric_differences(baseline, candidate)

    assert diff["recall_at_3"] == 0.05
    assert diff["source_category_match"] == 0.0622
    assert diff["context_pollution_rate"] == -0.1511
    assert diff["pollution_case_count"] == -9


def test_evaluation_scope_metadata_declares_positive_only_source_deduped_path():
    assert EVALUATION_SCOPE["evaluation_scope"] == "positive_only"
    assert EVALUATION_SCOPE["total_cases"] == 20
    assert EVALUATION_SCOPE["gate_applied"] is True
    assert EVALUATION_SCOPE["dedupe_level"] == "source"
    assert EVALUATION_SCOPE["direct_comparison_allowed"] == (
        "baseline_vs_reranker_v2_same_scope_only"
    )


def test_canonical_challenge_metrics_are_marked_not_directly_comparable():
    assert CANONICAL_CHALLENGE_V3_METRICS["scope"] == "40 cases: 20 positive + 20 negative"
    assert CANONICAL_CHALLENGE_V3_METRICS["directly_comparable_to_phase4b"] is False
    assert CANONICAL_CHALLENGE_V3_METRICS["precision_at_1"] == 0.325


def test_metric_definitions_record_precision_and_pollution_formulas():
    precision = METRIC_DEFINITIONS["precision_at_k"]
    pollution = METRIC_DEFINITIONS["context_pollution_rate"]
    source_match = METRIC_DEFINITIONS["source_category_match"]

    assert "deduped_retrieved_sources[:k]" in precision["per_case"]
    assert "average over the 20 positive development cases" == precision["aggregation"]
    assert "forbidden deduped sources" in pollution["per_case"]
    assert "weighted average with weight=max(1, source_count)" == pollution["aggregation"]
    assert "empty retrieval returns 1.0" in source_match["per_case"]


def test_gate_rejected_positive_metric_effect_is_explicit():
    rejected = METRIC_DEFINITIONS["gate_rejected_positive"]

    assert rejected["case_id"] == "gate_challenge_v3_data_privacy_004"
    assert "retrieval is empty" in rejected["behavior"]
    assert "Recall@K=0" in rejected["metric_effect"]
    assert "context_pollution_rate=0.0" in rejected["metric_effect"]


def test_compare_variants_records_corrections_and_recall_regressions():
    baseline = {
        "summary": {
            "recall_at_3": 0.95,
            "source_category_match": 0.4933,
            "context_pollution_rate": 0.3733,
        },
        "case_results": [
            _case("case-1", "data_privacy", ["data_privacy.md"], ["data_privacy.md", "service_outage.md"]),
            _case("case-2", "food_safety", ["food_safety.md"], ["food_safety.md"], recall_at_3=1.0),
        ],
    }
    candidate = {
        "summary": {
            "recall_at_3": DEVELOPMENT_SELECTION_RULE["recall_at_3_min"],
            "source_category_match": 0.6,
            "context_pollution_rate": 0.2,
        },
        "case_results": [
            _case("case-1", "data_privacy", ["data_privacy.md"], ["data_privacy.md"]),
            _case("case-2", "food_safety", ["food_safety.md"], [], recall_at_3=0.0),
        ],
    }

    comparison = compare_variants(baseline, candidate)

    assert comparison["corrected_wrong_candidates"][0]["corrected_sources"] == ["service_outage.md"]
    assert comparison["recall_regression_cases"][0]["case_id"] == "case-2"
    assert comparison["selection_checks"]["no_recall_regressions"] is False


def test_selection_rule_uses_same_scope_baseline_not_canonical_numbers():
    baseline = {
        "summary": {
            "recall_at_3": 0.95,
            "source_category_match": 0.8,
            "context_pollution_rate": 0.2,
        },
        "case_results": [
            _case("case-1", "data_privacy", ["data_privacy.md"], ["data_privacy.md"]),
        ],
    }
    candidate = {
        "summary": {
            "recall_at_3": DEVELOPMENT_SELECTION_RULE["recall_at_3_min"],
            "source_category_match": 0.7,
            "context_pollution_rate": 0.1,
        },
        "case_results": [
            _case("case-1", "data_privacy", ["data_privacy.md"], ["data_privacy.md"]),
        ],
    }

    comparison = compare_variants(baseline, candidate)

    assert comparison["selection_checks"]["context_pollution_rate"] is True
    assert comparison["selection_checks"]["source_category_match"] is False


def test_report_distinguishes_canonical_phase4b_and_phase4a_scopes():
    result = {
        "experiment": "Domain-Aware RuleBasedReranker Development",
        "dataset": "evaluation/rag_gate_challenge_v3.json",
        "scope": "post-hoc development only",
        "challenge_v3_status": "no longer untouched",
        "git_head": "abc123",
        "metric_scope": EVALUATION_SCOPE,
        "canonical_challenge_v3_metrics": CANONICAL_CHALLENGE_V3_METRICS,
        "phase4a_pollution_audit_scope": {
            "scope": "Challenge v3 positive cases, chunk-level trace",
            "gate_applied": False,
            "dedupe_level": "none",
            "retrieval_unit": "chunk",
            "purpose": "Locate pollution layers.",
        },
        "metric_definitions": METRIC_DEFINITIONS,
        "fixed_variables": ["Gate v3"],
        "baseline_formula": "old",
        "reranker_v2_formula": "v2",
        "development_selection_rule": DEVELOPMENT_SELECTION_RULE,
        "baseline": {
            "summary": {
                "wrong_rank_distribution": {},
                "confusion_pairs": {},
                "recall_at_3": 0.95,
                "context_pollution_rate": 0.4314,
                "source_category_match": 0.3921,
            }
        },
        "reranker_v2": {
            "summary": {
                "wrong_rank_distribution": {},
                "confusion_pairs": {},
                "recall_at_3": 0.95,
                "context_pollution_rate": 0.1765,
                "source_category_match": 0.5882,
            }
        },
        "comparison": {
            "metric_differences": {"recall_at_3": 0.0},
            "corrected_wrong_candidates": [],
            "newly_promoted_wrong_candidates": [],
            "recall_regression_cases": [],
            "selection_checks": {},
            "candidate_freeze_recommended": True,
        },
    }

    report = build_markdown_report(result)

    assert "NOT DIRECTLY COMPARABLE" in report
    assert "positive-only" in report
    assert "source-deduped" in report
    assert "Phase 4A wrong-rank distribution must not be compared directly" in report
