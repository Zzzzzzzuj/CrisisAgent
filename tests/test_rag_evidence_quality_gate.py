from backend.rag.evidence_quality_gate import evaluate_rag_evidence_quality


def _chunk(
    *,
    source_category: str = "food_safety",
    score: float | None = 0.8,
    rerank_score: float | None = 0.9,
) -> dict:
    chunk = {
        "chunk_id": "chunk-1",
        "document_id": "doc-1",
        "document_version": "1",
        "source_category": source_category,
        "text_preview": "证据片段",
    }
    if score is not None:
        chunk["score"] = score
    if rerank_score is not None:
        chunk["rerank_score"] = rerank_score
    return chunk


def test_no_evidence_marks_low_confidence_and_human_review():
    result = evaluate_rag_evidence_quality([])

    assert result["quality"] == "low"
    assert result["low_confidence"] is True
    assert result["should_trigger_human_review"] is True
    assert result["reasons"] == ["no_evidence"]
    assert result["evidence_count"] == 0


def test_fallback_used_marks_low_confidence():
    result = evaluate_rag_evidence_quality([_chunk()], fallback_used=True)

    assert result["quality"] == "low"
    assert result["low_confidence"] is True
    assert result["should_trigger_human_review"] is True
    assert "fallback_used" in result["reasons"]


def test_low_score_records_reason():
    result = evaluate_rag_evidence_quality([_chunk(score=0.05)])

    assert result["quality"] == "low"
    assert result["low_confidence"] is True
    assert "low_score" in result["reasons"]


def test_low_rerank_score_records_reason():
    result = evaluate_rag_evidence_quality([_chunk(rerank_score=0.03)])

    assert result["quality"] == "low"
    assert result["low_confidence"] is True
    assert "low_rerank_score" in result["reasons"]


def test_source_category_mismatch_calculates_pollution_rate():
    result = evaluate_rag_evidence_quality(
        [
            _chunk(source_category="food_safety"),
            _chunk(source_category="product_quality"),
        ],
        expected_source_category="food_safety",
    )

    assert result["quality"] == "medium"
    assert result["low_confidence"] is False
    assert result["context_precision"] == 0.5
    assert result["context_pollution_rate"] == 0.5
    assert "source_category_mismatch" in result["reasons"]


def test_high_context_pollution_triggers_human_review():
    result = evaluate_rag_evidence_quality(
        [
            _chunk(source_category="food_safety"),
            _chunk(source_category="product_quality"),
            _chunk(source_category="data_privacy"),
        ],
        expected_source_category="food_safety",
        max_context_pollution_rate=0.5,
    )

    assert result["quality"] == "low"
    assert result["low_confidence"] is True
    assert result["should_trigger_human_review"] is True
    assert result["context_precision"] == 1 / 3
    assert result["context_pollution_rate"] == 2 / 3
    assert "high_context_pollution" in result["reasons"]
    assert "source_category_mismatch" in result["reasons"]


def test_high_quality_evidence_does_not_mark_low_confidence():
    result = evaluate_rag_evidence_quality(
        [_chunk(), _chunk(score=0.7, rerank_score=0.8)],
        expected_source_category="food_safety",
    )

    assert result["quality"] == "high"
    assert result["low_confidence"] is False
    assert result["should_trigger_human_review"] is False
    assert result["reasons"] == []
    assert result["context_precision"] == 1.0
    assert result["context_pollution_rate"] == 0.0


def test_medium_quality_allows_minor_metadata_issue_without_low_confidence():
    result = evaluate_rag_evidence_quality(
        [_chunk(score=None), _chunk(score=0.7)],
        expected_source_category="food_safety",
    )

    assert result["quality"] == "medium"
    assert result["low_confidence"] is False
    assert result["should_trigger_human_review"] is False
    assert "missing_score" in result["reasons"]
