from backend.rag.reranker import RuleBasedReranker, rerank
from backend.rag.schemas import RetrievedChunk


def _chunk(
    chunk_id: str,
    text: str,
    score: float,
    source: str = "crisis_response.md",
    title: str = "Crisis Response",
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        text=text,
        source=source,
        title=title,
        score=score,
    )


def test_highly_relevant_chunk_can_rank_higher_after_rerank():
    chunks = [
        _chunk(
            "generic",
            "品牌回应需要保持透明。",
            0.9,
            source="crisis_response.md",
            title="危机回应规范",
        ),
        _chunk(
            "legal",
            "避免提前定责，使用条件式责任表达，不要在调查完成前确认违法。",
            0.6,
            source="legal_risk_rules.md",
            title="法律风险表达规则",
        ),
    ]

    result = rerank("避免提前定责和确认违法责任", chunks, top_k=2)

    assert result.chunks[0].chunk_id == "legal"
    assert result.chunks[0].rerank_score > result.chunks[1].rerank_score


def test_top_k_limits_reranked_results():
    chunks = [
        _chunk("chunk-1", "食品安全 监管", 0.7),
        _chunk("chunk-2", "法律风险 定责", 0.8),
        _chunk("chunk-3", "危机回应 共情", 0.6),
    ]

    result = RuleBasedReranker().rerank("危机回应", chunks, top_k=1)

    assert len(result.chunks) == 1
    assert len(result.sources) == 1


def test_rerank_score_exists_on_returned_chunks():
    chunks = [_chunk("chunk-1", "食品安全 监管", 0.7, source="food_safety.md", title="食品安全危机知识")]

    result = rerank("食品安全监管", chunks, top_k=1)

    assert result.chunks[0].rerank_score is not None
    assert result.sources[0]["rerank_score"] is not None
    assert "rerank_score" in result.context


def test_empty_chunks_return_empty_result():
    result = rerank("食品安全", [], top_k=3)

    assert result.context == ""
    assert result.chunks == []
    assert result.sources == []
