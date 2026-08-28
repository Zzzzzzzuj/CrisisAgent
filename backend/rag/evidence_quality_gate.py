from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def evaluate_rag_evidence_quality(
    evidence_chunks: Sequence[Mapping[str, Any]] | None,
    expected_source_category: str | None = None,
    min_score: float = 0.1,
    min_rerank_score: float = 0.1,
    max_context_pollution_rate: float = 0.5,
    fallback_used: bool = False,
) -> dict[str, Any]:
    """Assess whether Legal RAG evidence is reliable enough to use confidently.

    The gate is intentionally read-only: it does not re-rank, retrieve, or mutate
    evidence. It only turns existing metadata into an auditable confidence signal.
    """

    chunks = list(evidence_chunks or [])
    evidence_count = len(chunks)
    reasons: list[str] = []
    low_confidence = False
    context_precision: float | None = None
    context_pollution_rate: float | None = None

    if evidence_count == 0:
        return {
            "quality": "low",
            "low_confidence": True,
            "reasons": ["no_evidence"],
            "evidence_count": 0,
            "context_precision": None,
            "context_pollution_rate": None,
            "should_trigger_human_review": True,
        }

    if fallback_used:
        reasons.append("fallback_used")
        low_confidence = True

    low_score_count = 0
    low_rerank_score_count = 0
    missing_score_count = 0
    missing_rerank_score_count = 0

    for chunk in chunks:
        score = _as_float(_get(chunk, "score"))
        rerank_score = _as_float(_get(chunk, "rerank_score"))

        if score is None:
            missing_score_count += 1
        elif score < min_score:
            low_score_count += 1

        if rerank_score is None:
            missing_rerank_score_count += 1
        elif rerank_score < min_rerank_score:
            low_rerank_score_count += 1

    if low_score_count:
        reasons.append("low_score")
        low_confidence = True
    if low_rerank_score_count:
        reasons.append("low_rerank_score")
        low_confidence = True
    if missing_score_count:
        reasons.append("missing_score")
    if missing_rerank_score_count:
        reasons.append("missing_rerank_score")

    if expected_source_category:
        matched = sum(
            1
            for chunk in chunks
            if _normalize_category(_get(chunk, "source_category"))
            == _normalize_category(expected_source_category)
        )
        mismatched = evidence_count - matched
        context_precision = matched / evidence_count
        context_pollution_rate = mismatched / evidence_count

        if mismatched:
            reasons.append("source_category_mismatch")
        if context_pollution_rate > max_context_pollution_rate:
            reasons.append("high_context_pollution")
            low_confidence = True
        if mismatched > matched:
            low_confidence = True

    quality = _classify_quality(reasons, low_confidence)
    return {
        "quality": quality,
        "low_confidence": low_confidence,
        "reasons": reasons,
        "evidence_count": evidence_count,
        "context_precision": context_precision,
        "context_pollution_rate": context_pollution_rate,
        "should_trigger_human_review": low_confidence,
    }


def _classify_quality(reasons: list[str], low_confidence: bool) -> str:
    if low_confidence:
        return "low"
    if reasons:
        return "medium"
    return "high"


def _get(chunk: Mapping[str, Any], key: str) -> Any:
    if isinstance(chunk, Mapping):
        return chunk.get(key)
    return getattr(chunk, key, None)


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_category(value: Any) -> str:
    return str(value or "").strip().lower()
