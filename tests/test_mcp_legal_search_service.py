import pytest

from backend.mcp import legal_search_service
from backend.mcp.legal_search_service import search_law
from backend.rag.retriever import retrieve


def _retrieval_result() -> dict:
    return {
        "context": "[food_safety.md]\ncontext",
        "sources": [
            {
                "chunk_id": "food-1",
                "source": "food_safety.md",
                "title": "Food Safety",
                "score": 0.9,
                "rerank_score": 0.95,
                "source_category": "food_safety",
                "retrieval_backend": "markdown",
                "retrieval_type": "hybrid",
                "rerank_enabled": True,
                "retrieval_fallback": False,
            },
            {
                "chunk_id": "legal-1",
                "source": "legal_risk_rules.md",
                "title": "Legal Rules",
                "score": 0.8,
                "rerank_score": 0.85,
                "source_category": "legal_risk",
                "retrieval_backend": "markdown",
                "retrieval_type": "hybrid",
                "rerank_enabled": True,
                "retrieval_fallback": False,
            },
        ],
        "chunks": [
            {
                "chunk_id": "food-1",
                "source": "food_safety.md",
                "title": "Food Safety",
                "score": 0.9,
                "rerank_score": 0.95,
                "metadata": {
                    "document_id": "doc-food",
                    "document_version": "v1",
                    "source_category": "food_safety",
                    "document_status": "published",
                    "is_enabled": True,
                    "source_name": "food_safety.md",
                    "retrieval_backend": "markdown",
                    "retrieval_type": "hybrid",
                    "rerank_enabled": True,
                    "retrieval_fallback": False,
                },
                "text": "食品安全处置证据",
            },
            {
                "chunk_id": "legal-1",
                "source": "legal_risk_rules.md",
                "title": "Legal Rules",
                "score": 0.8,
                "rerank_score": 0.85,
                "metadata": {
                    "document_id": "doc-legal",
                    "document_version": "v1",
                    "source_category": "legal_risk",
                    "document_status": "published",
                    "is_enabled": True,
                    "source_name": "legal_risk_rules.md",
                    "retrieval_backend": "markdown",
                    "retrieval_type": "hybrid",
                    "rerank_enabled": True,
                    "retrieval_fallback": False,
                },
                "text": "法律风险处置证据",
            },
        ],
    }


def test_search_law_validates_query():
    with pytest.raises(ValueError, match="query must not be empty"):
        search_law("   ")

    with pytest.raises(TypeError, match="query must be a string"):
        search_law(123)  # type: ignore[arg-type]


def test_search_law_validates_top_k():
    with pytest.raises(ValueError, match="between 1 and 10"):
        search_law("食品安全", top_k=0)

    with pytest.raises(ValueError, match="between 1 and 10"):
        search_law("食品安全", top_k=11)

    with pytest.raises(TypeError, match="top_k must be an integer"):
        search_law("食品安全", top_k=True)  # type: ignore[arg-type]


def test_search_law_maps_retriever_metadata_and_preserves_order(monkeypatch):
    monkeypatch.setattr(legal_search_service, "retrieve", lambda query, top_k: _retrieval_result())

    result = search_law(" 某食品品牌被曝光使用过期原料 ", top_k=3, expected_source_category="food_safety")

    assert result["query"] == "某食品品牌被曝光使用过期原料"
    assert result["retrieval_status"] == "executed_with_hits"
    assert result["retrieval_backend"] == "markdown"
    assert result["retrieval_type"] == "hybrid"
    assert result["fallback_used"] is False
    assert result["sources"] == ["food_safety.md", "legal_risk_rules.md"]
    assert result["count"] == 2
    assert result["scores"] == [0.9, 0.8]
    assert result["rerank_scores"] == [0.95, 0.85]
    assert [chunk["chunk_id"] for chunk in result["evidence_chunks"]] == ["food-1", "legal-1"]
    assert result["evidence_chunks"][0]["document_id"] == "doc-food"
    assert result["evidence_chunks"][0]["source_category"] == "food_safety"
    assert result["evidence_quality"]["evaluated"] is True
    assert result["evidence_quality"]["context_precision"] == 0.5
    assert result["evidence_quality"]["context_pollution_rate"] == 0.5


def test_search_law_passes_expected_source_category_to_evidence_gate(monkeypatch):
    captured = {}
    monkeypatch.setattr(legal_search_service, "retrieve", lambda query, top_k: _retrieval_result())

    def fake_gate(**kwargs):
        captured.update(kwargs)
        return {"quality": "test"}

    monkeypatch.setattr(legal_search_service, "evaluate_rag_evidence_quality", fake_gate)

    result = search_law("食品安全", expected_source_category="food_safety")

    assert result["evidence_quality"] == {"quality": "test"}
    assert captured["expected_source_category"] == "food_safety"
    assert captured["fallback_used"] is False
    assert captured["evidence_chunks"][0]["chunk_id"] == "food-1"


def test_search_law_handles_no_hit(monkeypatch):
    monkeypatch.setattr(
        legal_search_service,
        "retrieve",
        lambda query, top_k: {"context": "", "sources": [], "chunks": []},
    )

    result = search_law("没有命中")

    assert result["retrieval_status"] == "executed_no_hit"
    assert result["count"] == 0
    assert result["evidence_chunks"] == []
    assert result["fallback_used"] is False
    assert result["evidence_quality"]["quality"] == "low"
    assert "no_evidence" in result["evidence_quality"]["reasons"]


def test_search_law_distinguishes_retrieval_exception_from_transport_failure(monkeypatch):
    def fail(query, top_k):
        raise RuntimeError("retriever unavailable")

    monkeypatch.setattr(legal_search_service, "retrieve", fail)

    result = search_law("食品安全", expected_source_category="food_safety")

    assert result["retrieval_status"] == "retrieval_error"
    assert result["fallback_used"] is True
    assert result["retrieval_backend"] == "none"
    assert result["error_type"] == "RuntimeError"
    assert "fallback_used" in result["evidence_quality"]["reasons"]
    assert "no_evidence" in result["evidence_quality"]["reasons"]


def test_search_law_real_retriever_parity_with_direct_path(monkeypatch):
    monkeypatch.setenv("CHECKPOINT_STORAGE", "json")
    monkeypatch.setenv("EMBEDDING_MODEL", "hash")
    monkeypatch.setenv("VECTOR_BACKEND", "json")
    query = "某食品品牌被曝光使用过期原料，消费者要求监管介入。"

    direct = retrieve(query, top_k=3)
    via_service = search_law(query, top_k=3, expected_source_category="food_safety")
    direct_normalized = legal_search_service._build_search_result(
        query=query,
        retrieval_result=direct,
        expected_source_category="food_safety",
    )

    assert [chunk["chunk_id"] for chunk in via_service["evidence_chunks"]] == [
        chunk["chunk_id"] for chunk in direct_normalized["evidence_chunks"]
    ]
    assert [chunk["source"] for chunk in via_service["evidence_chunks"]] == [
        chunk["source"] for chunk in direct_normalized["evidence_chunks"]
    ]
    assert via_service["source_details"] == direct_normalized["source_details"]
    assert via_service["scores"] == direct_normalized["scores"]
    assert via_service["rerank_scores"] == direct_normalized["rerank_scores"]
    assert via_service["count"] == direct_normalized["count"]
    assert via_service["fallback_used"] == direct_normalized["fallback_used"]
    assert via_service["retrieval_backend"] == direct_normalized["retrieval_backend"]
    assert via_service["retrieval_type"] == direct_normalized["retrieval_type"]
    assert via_service["evidence_quality"] == direct_normalized["evidence_quality"]
