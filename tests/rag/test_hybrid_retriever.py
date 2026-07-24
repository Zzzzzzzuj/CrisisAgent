from backend.rag.factory import get_retriever
from backend.rag.hybrid_retriever import HybridRetriever
from backend.rag.keyword_retriever import KeywordRetriever
from backend.rag.schemas import RetrievalResult, RetrievedChunk


class FakeRetriever:
    def __init__(self, chunks: list[RetrievedChunk]):
        self.chunks = chunks
        self.calls = []

    def retrieve(self, query: str, top_k: int = 3) -> RetrievalResult:
        self.calls.append({"query": query, "top_k": top_k})
        return RetrievalResult(context="fake context", chunks=self.chunks[:top_k], sources=[])


def _chunk(chunk_id: str, text: str, score: float, source: str = "test.md") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        text=text,
        source=source,
        title="Test",
        score=score,
    )


def test_hybrid_retriever_calls_keyword_and_vector_retrievers():
    keyword = FakeRetriever([_chunk("keyword-1", "keyword result", 0.8)])
    vector = FakeRetriever([_chunk("vector-1", "vector result", 0.7)])
    retriever = HybridRetriever(keyword_retriever=keyword, vector_retriever=vector)

    retriever.retrieve("食品安全", top_k=3)

    assert keyword.calls == [{"query": "食品安全", "top_k": 3}]
    assert vector.calls == [{"query": "食品安全", "top_k": 3}]


def test_hybrid_retriever_fuses_scores_with_configurable_weights():
    keyword = FakeRetriever([_chunk("same", "same chunk", 0.8)])
    vector = FakeRetriever([_chunk("same", "same chunk", 0.2)])
    retriever = HybridRetriever(
        keyword_retriever=keyword,
        vector_retriever=vector,
        keyword_weight=0.75,
        vector_weight=0.25,
    )

    result = retriever.retrieve("query", top_k=1)

    assert result.chunks[0].score == 0.65
    assert result.chunks[0].metadata["keyword_score"] == 0.8
    assert result.chunks[0].metadata["vector_score"] == 0.2


def test_hybrid_retriever_merges_duplicate_chunks():
    keyword = FakeRetriever([_chunk("same", "same chunk", 0.9)])
    vector = FakeRetriever([_chunk("same", "same chunk", 0.7)])
    retriever = HybridRetriever(keyword_retriever=keyword, vector_retriever=vector)

    result = retriever.retrieve("query", top_k=3)

    assert len(result.chunks) == 1
    assert result.chunks[0].chunk_id == "same"
    assert result.chunks[0].score == 0.8


def test_hybrid_retriever_top_k_limits_results():
    keyword = FakeRetriever(
        [
            _chunk("keyword-1", "keyword 1", 0.9),
            _chunk("keyword-2", "keyword 2", 0.8),
        ]
    )
    vector = FakeRetriever(
        [
            _chunk("vector-1", "vector 1", 1.0),
            _chunk("vector-2", "vector 2", 0.7),
        ]
    )
    retriever = HybridRetriever(keyword_retriever=keyword, vector_retriever=vector)

    result = retriever.retrieve("query", top_k=2)

    assert len(result.chunks) == 2
    assert len(result.sources) == 2


def test_hybrid_retriever_returns_compatible_result_shape():
    keyword = FakeRetriever([_chunk("keyword-1", "keyword result", 0.8)])
    vector = FakeRetriever([_chunk("vector-1", "vector result", 0.7)])
    retriever = HybridRetriever(keyword_retriever=keyword, vector_retriever=vector)

    result = retriever.retrieve("query", top_k=2)

    assert set(result.to_dict().keys()) == {"context", "chunks", "sources"}
    assert result.context
    assert result.sources


def test_factory_can_return_hybrid_retriever_without_changing_default():
    assert isinstance(get_retriever(), KeywordRetriever)
    assert isinstance(get_retriever("hybrid"), HybridRetriever)
