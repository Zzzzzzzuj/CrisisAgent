from backend.rag.base import BaseRetriever
from backend.rag.keyword_retriever import KeywordRetriever
from backend.rag.schemas import RetrievalResult, RetrievedChunk
from backend.rag.vector_retriever import VectorRetriever


class HybridRetriever(BaseRetriever):
    def __init__(
        self,
        keyword_retriever: BaseRetriever | None = None,
        vector_retriever: BaseRetriever | None = None,
        keyword_weight: float = 0.5,
        vector_weight: float = 0.5,
    ):
        self.keyword_retriever = keyword_retriever or KeywordRetriever()
        self.vector_retriever = vector_retriever or VectorRetriever()
        self.keyword_weight = keyword_weight
        self.vector_weight = vector_weight

    def retrieve(self, query: str, top_k: int = 3) -> RetrievalResult:
        if top_k <= 0:
            return RetrievalResult(context="", chunks=[], sources=[])

        keyword_result = self.keyword_retriever.retrieve(query, top_k=top_k)
        vector_result = self.vector_retriever.retrieve(query, top_k=top_k)
        merged_chunks = self._merge_chunks(keyword_result.chunks, vector_result.chunks)
        merged_chunks.sort(key=lambda chunk: chunk.score, reverse=True)
        top_chunks = merged_chunks[:top_k]

        return RetrievalResult(
            context=_format_context(top_chunks),
            chunks=top_chunks,
            sources=[
                {
                    "chunk_id": chunk.chunk_id,
                    "source": chunk.source,
                    "title": chunk.title,
                    "score": chunk.score,
                    "keyword_score": (chunk.metadata or {}).get("keyword_score", 0.0),
                    "vector_score": chunk.embedding_score or 0.0,
                    **_source_metadata(chunk),
                }
                for chunk in top_chunks
            ],
        )

    def _merge_chunks(
        self,
        keyword_chunks: list[RetrievedChunk],
        vector_chunks: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        merged: dict[str, dict] = {}

        for chunk in keyword_chunks:
            key = _chunk_key(chunk)
            merged[key] = {
                "chunk": chunk,
                "keyword_score": chunk.score,
                "vector_score": 0.0,
            }

        for chunk in vector_chunks:
            key = _chunk_key(chunk)
            if key not in merged:
                merged[key] = {
                    "chunk": chunk,
                    "keyword_score": 0.0,
                    "vector_score": chunk.score,
                }
            else:
                merged[key]["vector_score"] = chunk.score
                # Prefer chunk_id from vector search when keyword search has none.
                if not merged[key]["chunk"].chunk_id and chunk.chunk_id:
                    merged[key]["chunk"] = chunk

        return [
            _build_hybrid_chunk(
                item["chunk"],
                item["keyword_score"],
                item["vector_score"],
                self.keyword_weight,
                self.vector_weight,
            )
            for item in merged.values()
        ]


def _chunk_key(chunk: RetrievedChunk) -> str:
    if chunk.chunk_id:
        return chunk.chunk_id
    return f"{chunk.source}:{chunk.text}"


def _build_hybrid_chunk(
    chunk: RetrievedChunk,
    keyword_score: float,
    vector_score: float,
    keyword_weight: float,
    vector_weight: float,
) -> RetrievedChunk:
    final_score = keyword_weight * keyword_score + vector_weight * vector_score
    metadata = dict(chunk.metadata or {})
    metadata.update(
        {
            "retriever": "hybrid",
            "keyword_score": round(keyword_score, 4),
            "vector_score": round(vector_score, 4),
        }
    )

    return RetrievedChunk(
        chunk_id=chunk.chunk_id,
        text=chunk.text,
        source=chunk.source,
        title=chunk.title,
        score=round(final_score, 4),
        embedding_score=round(vector_score, 4),
        metadata=metadata,
    )


def _source_metadata(chunk: RetrievedChunk) -> dict:
    metadata = chunk.metadata or {}
    return {
        "document_id": metadata.get("document_id"),
        "document_version": metadata.get("document_version"),
        "source_category": metadata.get("source_category"),
    }


def _format_context(chunks: list[RetrievedChunk]) -> str:
    context_parts = []
    for chunk in chunks:
        context_parts.append(f"[{chunk.source} | score={chunk.score}]\n{chunk.text}")
    return "\n\n".join(context_parts)
