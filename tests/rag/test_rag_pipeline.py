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


class LowScoreHybridRetriever:
    def retrieve(self, query: str, top_k: int = 3) -> RetrievalResult:
        return RetrievalResult(
            context="low score context",
            chunks=[
                RetrievedChunk(
                    chunk_id="low-1",
                    text="unrelated basketball chunk",
                    source="unrelated.md",
                    title="Unrelated",
                    score=0.02,
                )
            ],
            sources=[],
        )


class ZeroScoreHybridRetriever:
    def retrieve(self, query: str, top_k: int = 3) -> RetrievalResult:
        return RetrievalResult(
            context="zero score context",
            chunks=[
                RetrievedChunk(
                    chunk_id="zero-1",
                    text="zero score chunk",
                    source="zero.md",
                    title="Zero",
                    score=0.0,
                )
            ],
            sources=[],
        )


class FixedScoreHybridRetriever:
    def retrieve(self, query: str, top_k: int = 3) -> RetrievalResult:
        return RetrievalResult(
            context="fixed score context",
            chunks=[
                RetrievedChunk(
                    chunk_id="medium",
                    text="food safety response",
                    source="food_safety.md",
                    title="Food Safety",
                    score=0.3,
                ),
                RetrievedChunk(
                    chunk_id="high",
                    text="legal safety response",
                    source="legal_risk_rules.md",
                    title="Legal",
                    score=0.8,
                ),
            ],
            sources=[],
        )


class PassThroughReranker:
    def rerank(self, query: str, chunks: list[RetrievedChunk], top_k: int = 3) -> RetrievalResult:
        top_chunks = chunks[:top_k]
        return RetrievalResult(
            context="pass through",
            chunks=top_chunks,
            sources=[
                {
                    "chunk_id": chunk.chunk_id,
                    "source": chunk.source,
                    "title": chunk.title,
                    "score": chunk.score,
                }
                for chunk in top_chunks
            ],
        )


class FixedReranker:
    def __init__(self, scores: dict[str, float]):
        self.scores = scores

    def rerank(self, query: str, chunks: list[RetrievedChunk], top_k: int = 3) -> RetrievalResult:
        reranked_chunks = [
            RetrievedChunk(
                chunk_id=chunk.chunk_id,
                text=chunk.text,
                source=chunk.source,
                title=chunk.title,
                score=chunk.score,
                rerank_score=self.scores[chunk.chunk_id],
            )
            for chunk in chunks
        ][:top_k]
        return RetrievalResult(
            context="fixed rerank",
            chunks=reranked_chunks,
            sources=[
                {
                    "chunk_id": chunk.chunk_id,
                    "source": chunk.source,
                    "title": chunk.title,
                    "score": chunk.score,
                    "rerank_score": chunk.rerank_score,
                }
                for chunk in reranked_chunks
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


def test_pipeline_filters_final_low_rerank_score_chunks():
    pipeline = RagPipelineRetriever(
        hybrid_retriever=LowScoreHybridRetriever(),
        reranker=FixedReranker({"low-1": 0.05}),
        min_rerank_score=0.1,
    )

    result = pipeline.retrieve("basketball query", top_k=3)

    assert result.context == ""
    assert result.chunks == []
    assert result.sources == []


def test_pipeline_filters_zero_score_chunks():
    pipeline = RagPipelineRetriever(
        hybrid_retriever=ZeroScoreHybridRetriever(),
        reranker=FixedReranker({"zero-1": 0.0}),
        min_rerank_score=0.1,
    )

    result = pipeline.retrieve("unrelated query", top_k=3)

    assert result.context == ""
    assert result.chunks == []
    assert result.sources == []


def test_pipeline_keeps_relevant_food_safety_results_after_threshold():
    result = retrieve("食品品牌使用过期原料，监管介入调查", top_k=3)

    assert result["chunks"]
    assert any(chunk["source"] == "food_safety.md" for chunk in result["chunks"])
    assert all(chunk["rerank_score"] >= 0.1 for chunk in result["chunks"])


def test_pipeline_min_rerank_score_is_configurable():
    low_threshold = RagPipelineRetriever(
        hybrid_retriever=FixedScoreHybridRetriever(),
        reranker=FixedReranker({"medium": 0.35, "high": 0.8}),
        min_rerank_score=0.3,
    )
    high_threshold = RagPipelineRetriever(
        hybrid_retriever=FixedScoreHybridRetriever(),
        reranker=FixedReranker({"medium": 0.35, "high": 0.8}),
        min_rerank_score=0.4,
    )

    low_result = low_threshold.retrieve("food safety", top_k=3)
    high_result = high_threshold.retrieve("food safety", top_k=3)

    assert {chunk.chunk_id for chunk in low_result.chunks} == {"medium", "high"}
    assert [chunk.chunk_id for chunk in high_result.chunks] == ["high"]


def test_pipeline_threshold_empty_result_is_not_keyword_fallback():
    pipeline = RagPipelineRetriever(
        hybrid_retriever=LowScoreHybridRetriever(),
        reranker=FixedReranker({"low-1": 0.05}),
        min_rerank_score=0.1,
    )

    result = pipeline.retrieve("basketball query", top_k=3)

    assert result.chunks == []
    assert result.sources == []
    assert result.context == ""


def test_pipeline_fallback_still_runs_when_hybrid_raises():
    pipeline = RagPipelineRetriever(
        hybrid_retriever=FailingHybridRetriever(),
        fallback_retriever=KeywordRetriever(),
        min_rerank_score=0.9,
    )

    result = pipeline.retrieve("食品安全监管", top_k=2)

    assert result.chunks
    assert result.chunks[0].metadata["retrieval_type"] == "keyword"
    assert result.chunks[0].metadata["retrieval_fallback"] is True


def test_pipeline_uses_chunk_score_when_rerank_score_is_missing():
    pipeline = RagPipelineRetriever(
        hybrid_retriever=FixedScoreHybridRetriever(),
        reranker=PassThroughReranker(),
        min_rerank_score=0.4,
    )

    result = pipeline.retrieve("food safety", top_k=3)

    assert [chunk.chunk_id for chunk in result.chunks] == ["high"]
    assert result.chunks[0].score == 0.8
    assert result.chunks[0].rerank_score is None


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
