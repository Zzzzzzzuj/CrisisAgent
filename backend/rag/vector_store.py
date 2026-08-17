import math
from copy import deepcopy
from typing import Any

from backend.rag.schemas import RetrievalResult, RetrievedChunk


class VectorStore:
    def __init__(self):
        self._chunks: list[dict[str, Any]] = []

    def add(self, chunks: list[dict]) -> None:
        for chunk in chunks:
            _validate_chunk(chunk)
            self._chunks.append(deepcopy(chunk))

    def search(self, query_embedding: list[float], top_k: int = 3) -> RetrievalResult:
        if top_k <= 0 or not self._chunks:
            return RetrievalResult(context="", chunks=[], sources=[])

        scored_chunks = []
        for chunk in self._chunks:
            score = _cosine_similarity(query_embedding, chunk["embedding"])
            scored_chunks.append((score, chunk))

        scored_chunks.sort(key=lambda item: item[0], reverse=True)
        top_chunks = scored_chunks[:top_k]

        retrieved_chunks = [
            RetrievedChunk(
                chunk_id=chunk["chunk_id"],
                text=chunk["text"],
                source=chunk["source"],
                title=chunk["title"],
                score=round(score, 4),
                embedding_score=round(score, 4),
                metadata={**dict(chunk.get("metadata", {})), "retriever": "vector"},
            )
            for score, chunk in top_chunks
        ]

        return RetrievalResult(
            context=_format_context(retrieved_chunks),
            chunks=retrieved_chunks,
            sources=[
                {
                    "chunk_id": chunk.chunk_id,
                    "source": chunk.source,
                    "title": chunk.title,
                    "score": chunk.score,
                    **_source_metadata(chunk),
                }
                for chunk in retrieved_chunks
            ],
        )


def _validate_chunk(chunk: dict) -> None:
    required_fields = ("chunk_id", "text", "source", "title", "embedding")
    missing_fields = [field for field in required_fields if field not in chunk]
    if missing_fields:
        raise ValueError(f"Vector chunk missing fields: {', '.join(missing_fields)}")
    if not isinstance(chunk["embedding"], list):
        raise TypeError("Vector chunk embedding must be a list.")


def _cosine_similarity(first: list[float], second: list[float]) -> float:
    if not first or not second or len(first) != len(second):
        return 0.0

    dot_product = sum(left * right for left, right in zip(first, second))
    first_norm = math.sqrt(sum(value * value for value in first))
    second_norm = math.sqrt(sum(value * value for value in second))

    if first_norm == 0 or second_norm == 0:
        return 0.0

    return dot_product / (first_norm * second_norm)


def _format_context(chunks: list[RetrievedChunk]) -> str:
    context_parts = []
    for chunk in chunks:
        context_parts.append(
            f"[{chunk.source} | chunk_id={chunk.chunk_id} | score={chunk.score}]\n{chunk.text}"
        )
    return "\n\n".join(context_parts)


def _source_metadata(chunk: RetrievedChunk) -> dict:
    metadata = chunk.metadata or {}
    return {
        "document_id": metadata.get("document_id"),
        "document_version": metadata.get("document_version"),
        "source_category": metadata.get("source_category"),
    }
