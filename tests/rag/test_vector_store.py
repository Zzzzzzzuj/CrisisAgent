from backend.rag.embedding import HashEmbeddingModel
from backend.rag.vector_store import VectorStore


def _chunk(chunk_id: str, text: str, source: str = "test.md") -> dict:
    model = HashEmbeddingModel(dimension=64)
    return {
        "chunk_id": chunk_id,
        "text": text,
        "source": source,
        "title": "Test Knowledge",
        "embedding": model.embed(text),
    }


def test_vector_store_can_search_after_adding_chunks():
    model = HashEmbeddingModel(dimension=64)
    store = VectorStore()
    store.add(
        [
            _chunk("chunk-1", "食品安全危机需要配合监管调查", "food_safety.md"),
            _chunk("chunk-2", "品牌回应需要先共情再说明行动", "crisis_response.md"),
        ]
    )

    result = store.search(model.embed("食品安全 监管 调查"), top_k=2)

    assert result.context
    assert len(result.chunks) == 2
    assert result.sources
    assert result.chunks[0].chunk_id


def test_similar_text_ranks_higher():
    model = HashEmbeddingModel(dimension=64)
    store = VectorStore()
    store.add(
        [
            _chunk("food", "食品安全 过期原料 监管 调查", "food_safety.md"),
            _chunk("legal", "避免提前定责 使用条件式责任表达", "legal_risk_rules.md"),
        ]
    )

    result = store.search(model.embed("食品 过期原料 监管"), top_k=2)

    assert result.chunks[0].chunk_id == "food"
    assert result.chunks[0].score >= result.chunks[1].score


def test_top_k_limits_results():
    model = HashEmbeddingModel(dimension=64)
    store = VectorStore()
    store.add(
        [
            _chunk("chunk-1", "食品安全"),
            _chunk("chunk-2", "危机回应"),
            _chunk("chunk-3", "法律风险"),
        ]
    )

    result = store.search(model.embed("危机"), top_k=1)

    assert len(result.chunks) == 1
    assert len(result.sources) == 1


def test_empty_store_search_returns_empty_result():
    model = HashEmbeddingModel(dimension=64)
    store = VectorStore()

    result = store.search(model.embed("食品安全"), top_k=3)

    assert result.context == ""
    assert result.chunks == []
    assert result.sources == []
