from pathlib import Path

import pytest

from backend.rag.schemas import RetrievalResult, RetrievedChunk
from evaluation import rag_retrieval_holdout_v1_evaluator as evaluator


def _chunk(source, score=0.5, chunk_id=None, title="Title", text="content"):
    return RetrievedChunk(
        chunk_id=chunk_id or source,
        source=source,
        title=title,
        text=text,
        score=score,
        embedding_score=score,
        metadata={"keyword_score": score, "vector_score": score},
    )


def _case(category="food_safety"):
    return {
        "case_id": "case-1",
        "category": category,
        "event": "current crisis event",
        "expected_retrieval": True,
        "acceptable_sources": [f"{category}.md"],
        "neutral_sources": ["crisis_response.md", "legal_risk_rules.md"],
        "forbidden_sources": [
            source for source in [
                "food_safety.md",
                "data_privacy.md",
                "service_outage.md",
                "product_quality.md",
                "executive_misconduct.md",
            ]
            if source != f"{category}.md"
        ],
    }


class FakeHybridRetriever:
    def __init__(self, chunks):
        self.chunks = chunks
        self.calls = []

    def retrieve(self, query, top_k=5):
        self.calls.append({"query": query, "top_k": top_k})
        top_chunks = self.chunks[:top_k]
        return RetrievalResult(
            context="",
            chunks=top_chunks,
            sources=[{"source": chunk.source, "score": chunk.score} for chunk in top_chunks],
        )


class RecordingReranker:
    def __init__(self):
        self.calls = []

    def rerank(self, query, chunks, top_k=5):
        self.calls.append(
            {
                "query": query,
                "chunks": evaluator.candidate_pool_signature(chunks),
                "chunk_objects": chunks,
            }
        )
        top_chunks = chunks[:top_k]
        return RetrievalResult(
            context="",
            chunks=top_chunks,
            sources=[evaluator._source_dict(chunk) for chunk in top_chunks],
        )


class GoldRejectingReranker(RecordingReranker):
    def rerank(self, query, chunks, top_k=5):
        forbidden_names = {
            "category",
            "acceptable_sources",
            "neutral_sources",
            "forbidden_sources",
            "case_id",
        }
        assert not any(name in query for name in forbidden_names)
        for chunk in chunks:
            metadata = chunk.metadata or {}
            assert forbidden_names.isdisjoint(metadata)
        return super().rerank(query, chunks, top_k)


class OrderedReranker:
    def __init__(self, source_order):
        self.source_order = source_order

    def rerank(self, query, chunks, top_k=5):
        by_source = {chunk.source: chunk for chunk in chunks}
        ordered = [by_source[source] for source in self.source_order if source in by_source]
        ordered.extend(chunk for chunk in chunks if chunk.source not in self.source_order)
        top_chunks = ordered[:top_k]
        return RetrievalResult(
            context="",
            chunks=top_chunks,
            sources=[evaluator._source_dict(chunk) for chunk in top_chunks],
        )


def test_holdout_dataset_has_30_cases_and_five_categories_each_six():
    cases = evaluator.load_holdout_cases()

    assert len(cases) == 30
    counts = {}
    for case in cases:
        counts[case["category"]] = counts.get(case["category"], 0) + 1
    assert counts == {
        "food_safety": 6,
        "data_privacy": 6,
        "service_outage": 6,
        "product_quality": 6,
        "executive_misconduct": 6,
    }


def test_source_groups_are_mutually_exclusive_and_expected_retrieval_true():
    for case in evaluator.load_holdout_cases():
        assert case["expected_retrieval"] is True
        groups = [
            set(case["acceptable_sources"]),
            set(case["neutral_sources"]),
            set(case["forbidden_sources"]),
        ]
        assert not groups[0] & groups[1]
        assert not groups[0] & groups[2]
        assert not groups[1] & groups[2]


def test_gate_is_not_imported_or_called_by_holdout_evaluator(monkeypatch, tmp_path):
    def fail_import(name, *args, **kwargs):
        if name == "backend.rag.retrieval_need_gate":
            raise AssertionError("Gate must not be imported.")
        return original_import(name, *args, **kwargs)

    original_import = __import__
    monkeypatch.setattr("builtins.__import__", fail_import)

    cases = [_case()]
    fake_hybrid = FakeHybridRetriever([_chunk("food_safety.md")])
    result = evaluator.run_holdout_evaluation(
        holdout_path=_write_cases(tmp_path, cases),
        hybrid_retriever=fake_hybrid,
        old_reranker=RecordingReranker(),
        v2_reranker=RecordingReranker(),
        validate=False,
    )

    assert result["metric_scope"]["gate_applied"] is False


def test_gold_fields_are_not_passed_to_reranker(tmp_path):
    cases = [_case()]
    fake_hybrid = FakeHybridRetriever([_chunk("food_safety.md")])

    result = evaluator.run_holdout_evaluation(
        holdout_path=_write_cases(tmp_path, cases),
        hybrid_retriever=fake_hybrid,
        old_reranker=GoldRejectingReranker(),
        v2_reranker=GoldRejectingReranker(),
        validate=False,
    )

    assert result["candidate_pool_parity"] is True


def test_old_baseline_formula_is_frozen():
    assert evaluator.FrozenOldRuleBasedReranker.formula == (
        "0.5 * retrieval_score + 0.2 * title_match "
        "+ 0.15 * source_match + 0.15 * keyword_overlap"
    )


def test_old_and_v2_candidate_pool_inputs_are_identical(tmp_path):
    cases = [_case()]
    fake_hybrid = FakeHybridRetriever([
        _chunk("food_safety.md", score=0.8),
        _chunk("product_quality.md", score=0.6),
    ])
    old = RecordingReranker()
    v2 = RecordingReranker()

    result = evaluator.run_holdout_evaluation(
        holdout_path=_write_cases(tmp_path, cases),
        hybrid_retriever=fake_hybrid,
        old_reranker=old,
        v2_reranker=v2,
        validate=False,
    )

    assert result["candidate_pool_parity"] is True
    assert old.calls[0]["chunks"] == v2.calls[0]["chunks"]
    assert old.calls[0]["chunk_objects"] is not v2.calls[0]["chunk_objects"]


def test_source_dedupe_preserves_first_source_order():
    sources = ["food_safety.md", "food_safety.md", "crisis_response.md"]

    assert evaluator.dedupe_sources(sources) == ["food_safety.md", "crisis_response.md"]


def test_recall_precision_and_mrr_formulas():
    sources = ["wrong.md", "food_safety.md", "neutral.md"]
    acceptable = {"food_safety.md"}

    assert evaluator.calculate_recall_at_k(sources, acceptable, 1) == 0.0
    assert evaluator.calculate_recall_at_k(sources, acceptable, 3) == 1.0
    assert evaluator.calculate_precision_at_k(sources, acceptable, 3) == 0.3333
    assert evaluator.calculate_reciprocal_rank(sources, acceptable) == 0.5


def test_scm_denominator_zero_and_empty_retrieval_are_zero():
    assert evaluator.calculate_source_category_match([], {"food_safety.md"}, {"wrong.md"}) == 0.0
    assert evaluator.calculate_source_category_match(["crisis_response.md"], {"food_safety.md"}, {"wrong.md"}) == 0.0
    metrics = evaluator.calculate_case_metrics(
        [],
        ["food_safety.md"],
        ["crisis_response.md"],
        ["product_quality.md"],
    )
    assert metrics["recall_at_3"] == 0.0
    assert metrics["reciprocal_rank"] == 0.0
    assert metrics["source_category_match"] == 0.0
    assert metrics["context_pollution_rate"] == 0.0


def test_pollution_formula_counts_forbidden_over_all_returned_labeled_sources():
    sources = ["food_safety.md", "crisis_response.md", "product_quality.md"]

    pollution = evaluator.calculate_context_pollution_rate(
        sources,
        {"food_safety.md"},
        {"crisis_response.md"},
        {"product_quality.md"},
    )

    assert pollution == 0.3333


def test_relative_pollution_reduction_handles_zero_old_pollution():
    assert evaluator.calculate_relative_pollution_reduction(0.0, 0.0) is None
    assert evaluator.calculate_relative_pollution_reduction(0.5, 0.25) == 0.5


def test_top3_regression_and_improvement_count(tmp_path):
    cases = [_case()]
    chunks = [
        _chunk("food_safety.md"),
        _chunk("product_quality.md"),
        _chunk("data_privacy.md"),
        _chunk("service_outage.md"),
        _chunk("executive_misconduct.md"),
    ]
    fake_hybrid = FakeHybridRetriever(chunks)

    regression = evaluator.run_holdout_evaluation(
        holdout_path=_write_cases(tmp_path, cases),
        hybrid_retriever=fake_hybrid,
        old_reranker=OrderedReranker(["food_safety.md", "product_quality.md"]),
        v2_reranker=OrderedReranker([
            "product_quality.md",
            "data_privacy.md",
            "service_outage.md",
            "executive_misconduct.md",
            "food_safety.md",
        ]),
        validate=False,
    )
    assert regression["comparison"]["new_top3_regression_count"] == 1

    improvement = evaluator.run_holdout_evaluation(
        holdout_path=_write_cases(tmp_path, cases),
        hybrid_retriever=fake_hybrid,
        old_reranker=OrderedReranker([
            "product_quality.md",
            "data_privacy.md",
            "service_outage.md",
            "executive_misconduct.md",
            "food_safety.md",
        ]),
        v2_reranker=OrderedReranker(["food_safety.md"]),
        validate=False,
    )
    assert improvement["comparison"]["improvement_cases"][0]["case_id"] == "case-1"


def test_per_domain_recall_at_3_is_reported(tmp_path):
    cases = [_case("food_safety"), _case("data_privacy")]
    chunks = [_chunk("food_safety.md"), _chunk("data_privacy.md")]
    result = evaluator.run_holdout_evaluation(
        holdout_path=_write_cases(tmp_path, cases),
        hybrid_retriever=FakeHybridRetriever(chunks),
        old_reranker=RecordingReranker(),
        v2_reranker=RecordingReranker(),
        validate=False,
    )

    assert result["comparison"]["per_domain_v2"]["food_safety"]["recall_at_3"] == 1.0
    assert result["comparison"]["per_domain_v2"]["data_privacy"]["recall_at_3"] == 1.0


def test_acceptance_criteria_pass_and_fail():
    old_summary = {
        "recall_at_3": 0.95,
        "context_pollution_rate": 0.5,
        "source_category_match": 0.4,
    }
    v2_summary = {
        "recall_at_3": 0.95,
        "context_pollution_rate": 0.3,
        "source_category_match": 0.6,
    }
    comparison = {
        "pollution_relative_reduction": 0.4,
        "new_top3_regression_count": 0,
        "per_domain_v2": {"food_safety": {"recall_at_3": 0.75}},
    }

    acceptance = evaluator.evaluate_acceptance(old_summary, v2_summary, comparison)
    assert acceptance["status"] == "PASS"

    comparison["new_top3_regression_count"] = 3
    acceptance = evaluator.evaluate_acceptance(old_summary, v2_summary, comparison)
    assert acceptance["checks"]["new_top3_regression_cases_lte_2"] is False
    assert acceptance["status"] == "FAIL"


def test_holdout_and_protocol_are_not_modified_by_fake_evaluation(tmp_path):
    holdout = Path("evaluation/rag_retrieval_holdout_v1.json")
    protocol = Path("evaluation/reports/rag_retrieval_holdout_v1_protocol.md")
    before_holdout = holdout.read_text(encoding="utf-8")
    before_protocol = protocol.read_text(encoding="utf-8")

    evaluator.run_holdout_evaluation(
        holdout_path=_write_cases(tmp_path, [_case()]),
        hybrid_retriever=FakeHybridRetriever([_chunk("food_safety.md")]),
        old_reranker=RecordingReranker(),
        v2_reranker=RecordingReranker(),
        validate=False,
    )

    assert holdout.read_text(encoding="utf-8") == before_holdout
    assert protocol.read_text(encoding="utf-8") == before_protocol


def test_disabled_fallback_retriever_raises_instead_of_faking_bge_success():
    with pytest.raises(RuntimeError, match="Fallback is disabled"):
        evaluator.DisabledFallbackRetriever().retrieve("query")


def _write_cases(tmp_path, cases):
    path = tmp_path / "holdout_cases.json"
    path.write_text(__import__("json").dumps(cases, ensure_ascii=False), encoding="utf-8")
    return path
