from backend.rag.factory import get_retriever
from backend.rag.keyword_retriever import KeywordRetriever
from backend.rag.pipeline_retriever import RagPipelineRetriever
from backend.rag.retriever import retrieve
from backend.rag.schemas import RetrievalResult, RetrievedChunk


class FakeHybridRetriever:
    def __init__(self):
        self.calls = []

    def retrieve(self, query: str, top_k: int = 3) -> RetrievalResult:
        self.calls.append({"query": query, "top_k": top_k})
        return RetrievalResult(
            context="hybrid context",
            chunks=[
                RetrievedChunk(
                    chunk_id="hybrid-1",
                    text="食品安全监管回应",
                    source="food_safety.md",
                    title="食品安全危机知识",
                    score=0.7,
                )
            ],
            sources=[],
        )


class FakeReranker:
    def __init__(self):
        self.calls = []

    def rerank(self, query: str, chunks: list[RetrievedChunk], top_k: int = 3) -> RetrievalResult:
        self.calls.append({"query": query, "top_k": top_k, "chunk_count": len(chunks)})
        reranked_chunk = RetrievedChunk(
            chunk_id=chunks[0].chunk_id,
            text=chunks[0].text,
            source=chunks[0].source,
            title=chunks[0].title,
            score=chunks[0].score,
            rerank_score=0.95,
        )
        return RetrievalResult(
            context="reranked context",
            chunks=[reranked_chunk],
            sources=[
                {
                    "chunk_id": reranked_chunk.chunk_id,
                    "source": reranked_chunk.source,
                    "title": reranked_chunk.title,
                    "score": reranked_chunk.score,
                    "rerank_score": reranked_chunk.rerank_score,
                }
            ],
        )


class FailingHybridRetriever:
    def retrieve(self, query: str, top_k: int = 3) -> RetrievalResult:
        raise RuntimeError("vector path failed")


def test_pipeline_retriever_calls_hybrid_then_reranker():
    hybrid = FakeHybridRetriever()
    reranker = FakeReranker()
    pipeline = RagPipelineRetriever(hybrid_retriever=hybrid, reranker=reranker)

    result = pipeline.retrieve("食品安全监管", top_k=1)

    assert hybrid.calls[0] == {"query": "食品安全监管", "top_k": 1}
    assert len(hybrid.calls) >= 1
    assert reranker.calls == [{"query": "食品安全监管", "top_k": 1, "chunk_count": 1}]
    assert result.chunks[0].rerank_score == 0.95
    assert result.chunks[0].metadata["retrieval_type"] == "hybrid"
    assert result.chunks[0].metadata["rerank_enabled"] is True


def test_default_retrieve_entrypoint_returns_rerank_score():
    result = retrieve("食品安全监管回应", top_k=2)

    assert "context" in result
    assert "chunks" in result
    assert "sources" in result
    assert result["chunks"]
    assert "rerank_score" in result["chunks"][0]
    assert result["chunks"][0]["metadata"]["retrieval_type"] == "hybrid"
    assert result["chunks"][0]["metadata"]["rerank_enabled"] is True


def test_pipeline_falls_back_to_keyword_when_hybrid_or_rerank_fails():
    pipeline = RagPipelineRetriever(
        hybrid_retriever=FailingHybridRetriever(),
        fallback_retriever=KeywordRetriever(),
    )

    result = pipeline.retrieve("食品安全监管", top_k=2)

    assert result.chunks
    assert result.chunks[0].metadata["retrieval_type"] == "keyword"
    assert result.chunks[0].metadata["rerank_enabled"] is False
    assert result.chunks[0].metadata["retrieval_fallback"] is True


def test_agent_b_legacy_retrieve_call_shape_is_compatible():
    result = retrieve("避免提前定责 使用条件式责任表达", top_k=3)

    assert isinstance(result, dict)
    assert set(result.keys()) == {"context", "chunks", "sources"}
    assert isinstance(result["context"], str)
    assert isinstance(result["chunks"], list)
    assert isinstance(result["sources"], list)


def test_factory_can_return_pipeline_without_changing_default_keyword():
    assert isinstance(get_retriever(), KeywordRetriever)
    assert isinstance(get_retriever("pipeline"), RagPipelineRetriever)
