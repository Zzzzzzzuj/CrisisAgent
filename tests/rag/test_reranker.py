import inspect

from backend.rag.reranker import RuleBasedReranker, rerank
from backend.rag.schemas import RetrievedChunk
from evaluation.reranker_v2_development import BaselineRuleBasedReranker


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
    chunks = [
        _chunk(
            "chunk-1",
            "食品安全 监管",
            0.7,
            source="food_safety.md",
            title="食品安全危机知识",
        )
    ]

    result = rerank("食品安全监管", chunks, top_k=1)

    assert result.chunks[0].rerank_score is not None
    assert result.sources[0]["rerank_score"] is not None
    assert "rerank_score" in result.context


def test_empty_chunks_return_empty_result():
    result = rerank("食品安全", [], top_k=3)

    assert result.context == ""
    assert result.chunks == []
    assert result.sources == []


def test_reranker_signature_does_not_accept_evaluation_gold():
    signature = inspect.signature(RuleBasedReranker().rerank)

    assert "category" not in signature.parameters
    assert "acceptable_sources" not in signature.parameters


def test_same_domain_candidate_receives_ranking_benefit():
    chunks = [
        _chunk(
            "privacy",
            "个人信息访问记录异常，需要核查受影响用户范围。",
            0.4,
            source="data_privacy.md",
            title="数据安全事件处置",
        ),
        _chunk(
            "quality",
            "产品外壳发热，需要安排检测和退换处理。",
            0.42,
            source="product_quality.md",
            title="产品质量处理",
        ),
    ]

    result = rerank("用户手机号和地址被陌生账号看到，需要准备通知。", chunks, top_k=2)

    assert result.chunks[0].chunk_id == "privacy"
    assert result.chunks[0].metadata["domain_adjustment"] > 0


def test_obvious_cross_domain_candidate_receives_limited_penalty():
    chunks = [
        _chunk(
            "wrong",
            "产品发热鼓起，需要检测和退换。",
            0.6,
            source="product_quality.md",
            title="产品质量处理",
        )
    ]

    result = rerank("用户手机号和地址出现在陌生账号，平台需要通知用户。", chunks, top_k=1)

    assert result.chunks[0].metadata["domain_adjustment"] < 0
    assert result.chunks[0].rerank_score > 0


def test_multi_domain_candidate_is_not_hard_filtered():
    chunks = [
        _chunk(
            "service",
            "支付系统异常导致订单不同步，需要发布恢复进展。",
            0.4,
            source="service_outage.md",
            title="服务异常处置",
        ),
        _chunk(
            "privacy",
            "用户数据访问记录异常，需要核查影响范围。",
            0.38,
            source="data_privacy.md",
            title="数据安全处置",
        ),
    ]

    result = rerank("支付系统异常同时涉及用户数据，需要准备说明。", chunks, top_k=2)

    assert {chunk.chunk_id for chunk in result.chunks} == {"service", "privacy"}
    assert all(chunk.rerank_score is not None for chunk in result.chunks)


def test_unknown_domain_stays_neutral():
    chunks = [_chunk("unknown", "品牌需要准备说明并同步处理安排。", 0.5)]

    result = rerank("品牌需要准备说明。", chunks, top_k=1)

    assert result.chunks[0].metadata["query_domains"] == []
    assert result.chunks[0].metadata["domain_adjustment"] == 0.0


def test_baseline_reranker_reproduces_original_formula():
    chunks = [
        _chunk(
            "base",
            "品牌回应透明",
            0.8,
            source="crisis_response.md",
            title="Crisis Response",
        )
    ]

    result = BaselineRuleBasedReranker().rerank("unrelated query", chunks, top_k=1)

    assert result.chunks[0].rerank_score == 0.4


def test_domain_aware_reranker_is_deterministic():
    chunks = [
        _chunk(
            "privacy",
            "用户个人信息异常访问，需要核查。",
            0.4,
            source="data_privacy.md",
            title="数据安全",
        ),
        _chunk(
            "quality",
            "产品发热鼓起，需要检测。",
            0.4,
            source="product_quality.md",
            title="产品质量",
        ),
    ]

    first = rerank("用户个人信息被陌生账号看到。", chunks, top_k=2)
    second = rerank("用户个人信息被陌生账号看到。", chunks, top_k=2)

    assert [chunk.to_dict() for chunk in first.chunks] == [
        chunk.to_dict() for chunk in second.chunks
    ]
