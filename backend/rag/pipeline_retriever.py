from backend.logger import get_logger
from backend.rag.base import BaseRetriever
from backend.rag.hybrid_retriever import HybridRetriever
from backend.rag.keyword_retriever import KeywordRetriever
from backend.rag.query_rewriter import rewrite_query
from backend.rag.reranker import RuleBasedReranker
from backend.rag.schemas import RetrievalResult, RetrievedChunk


logger = get_logger(__name__)


class RagPipelineRetriever(BaseRetriever):
    def __init__(
        self,
        hybrid_retriever: BaseRetriever | None = None,
        reranker: RuleBasedReranker | None = None,
        fallback_retriever: BaseRetriever | None = None,
        min_rerank_score: float = 0.1,
    ):
        self.hybrid_retriever = hybrid_retriever or HybridRetriever()
        self.reranker = reranker or RuleBasedReranker()
        self.fallback_retriever = fallback_retriever or KeywordRetriever()
        self.min_rerank_score = min_rerank_score

    def retrieve(self, query: str, top_k: int = 3) -> RetrievalResult:
        try:
            rewritten_queries = rewrite_query(query)
            hybrid_chunks = []
            for rewritten_query in rewritten_queries:
                hybrid_result = self.hybrid_retriever.retrieve(rewritten_query, top_k=top_k)
                hybrid_chunks.extend(
                    _copy_chunk_with_query_metadata(chunk, rewritten_query, rewritten_queries)
                    for chunk in hybrid_result.chunks
                )

            merged_chunks = _merge_rewritten_chunks(hybrid_chunks)
            reranked_result = self.reranker.rerank(query, merged_chunks, top_k=top_k)
            filtered_result = _filter_by_min_relevance(reranked_result, self.min_rerank_score)
            return _with_pipeline_metadata(
                filtered_result,
                retrieval_type="hybrid",
                rerank_enabled=True,
                fallback=False,
            )
        except Exception as exc:
            logger.warning(
                "RAG pipeline fallback to keyword retrieval: %s | %s",
                exc.__class__.__name__,
                str(exc),
            )
            fallback_result = self.fallback_retriever.retrieve(query, top_k=top_k)
            return _with_pipeline_metadata(
                fallback_result,
                retrieval_type="keyword",
                rerank_enabled=False,
                fallback=True,
            )


def _with_pipeline_metadata(
    result: RetrievalResult,
    retrieval_type: str,
    rerank_enabled: bool,
    fallback: bool,
) -> RetrievalResult:
    chunks = [
        _copy_chunk_with_metadata(chunk, retrieval_type, rerank_enabled, fallback)
        for chunk in result.chunks
    ]
    return RetrievalResult(
        context=result.context,
        chunks=chunks,
        sources=[
            {
                **source,
                "retrieval_type": retrieval_type,
                "rerank_enabled": rerank_enabled,
                "retrieval_fallback": fallback,
            }
            for source in result.sources
        ],
    )


def _filter_by_min_relevance(result: RetrievalResult, min_score: float) -> RetrievalResult:
    kept_chunks = [
        chunk for chunk in result.chunks
        if _final_relevance_score(chunk) >= min_score
    ]
    return RetrievalResult(
        context=_format_context(kept_chunks),
        chunks=kept_chunks,
        sources=[
            {
                "chunk_id": chunk.chunk_id,
                "source": chunk.source,
                "title": chunk.title,
                "score": chunk.score,
                "rerank_score": chunk.rerank_score,
                **_source_metadata(chunk),
            }
            for chunk in kept_chunks
        ],
    )


def _final_relevance_score(chunk: RetrievedChunk) -> float:
    metadata = chunk.metadata or {}
    score = metadata.get("rerank_score", chunk.rerank_score)
    if score is None:
        score = chunk.score
    return float(score or 0.0)


def _copy_chunk_with_query_metadata(
    chunk: RetrievedChunk,
    matched_query: str,
    rewritten_queries: list[str],
) -> RetrievedChunk:
    metadata = dict(chunk.metadata or {})
    metadata.update(
        {
            "query_rewrite_enabled": True,
            "matched_query": matched_query,
            "rewritten_queries": list(rewritten_queries),
        }
    )
    return RetrievedChunk(
        chunk_id=chunk.chunk_id,
        text=chunk.text,
        source=chunk.source,
        title=chunk.title,
        score=chunk.score,
        metadata=metadata,
        embedding_score=chunk.embedding_score,
        rerank_score=chunk.rerank_score,
    )


def _format_context(chunks: list[RetrievedChunk]) -> str:
    context_parts = []
    for chunk in chunks:
        context_parts.append(
            f"[{chunk.source} | score={chunk.score} | rerank_score={chunk.rerank_score}]\n{chunk.text}"
        )
    return "\n\n".join(context_parts)


def _merge_rewritten_chunks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    merged: dict[str, RetrievedChunk] = {}
    for chunk in chunks:
        key = chunk.chunk_id or f"{chunk.source}:{chunk.text}"
        existing = merged.get(key)
        if existing is None or chunk.score > existing.score:
            merged[key] = chunk

    return sorted(merged.values(), key=lambda item: item.score, reverse=True)


def _copy_chunk_with_metadata(
    chunk: RetrievedChunk,
    retrieval_type: str,
    rerank_enabled: bool,
    fallback: bool,
) -> RetrievedChunk:
    metadata = dict(chunk.metadata or {})
    metadata.update(
        {
            "retrieval_type": retrieval_type,
            "rerank_enabled": rerank_enabled,
            "retrieval_fallback": fallback,
            "rerank_score": chunk.rerank_score,
        }
    )
    return RetrievedChunk(
        chunk_id=chunk.chunk_id,
        text=chunk.text,
        source=chunk.source,
        title=chunk.title,
        score=chunk.score,
        metadata=metadata,
        embedding_score=chunk.embedding_score,
        rerank_score=chunk.rerank_score,
    )


def _source_metadata(chunk: RetrievedChunk) -> dict:
    metadata = chunk.metadata or {}
    return {
        "document_id": metadata.get("document_id"),
        "document_version": metadata.get("document_version"),
        "source_category": metadata.get("source_category"),
    }
