from __future__ import annotations

from typing import Any

from backend.rag.evidence_quality_gate import evaluate_rag_evidence_quality
from backend.rag.retriever import retrieve


def search_law(
    query: str,
    top_k: int = 3,
    expected_source_category: str | None = None,
) -> dict[str, Any]:
    """Expose the existing Legal RAG retrieval path as a pure Python service."""

    clean_query = _validate_query(query)
    clean_top_k = _validate_top_k(top_k)

    try:
        retrieval_result = retrieve(clean_query, clean_top_k)
    except Exception as exc:
        evidence_quality = evaluate_rag_evidence_quality(
            evidence_chunks=[],
            expected_source_category=expected_source_category,
            fallback_used=True,
        )
        return {
            "query": clean_query,
            "evidence_chunks": [],
            "sources": [],
            "source_details": [],
            "scores": [],
            "rerank_scores": [],
            "count": 0,
            "fallback_used": True,
            "retrieval_backend": "none",
            "retrieval_type": None,
            "retrieval_status": "retrieval_error",
            "error_type": exc.__class__.__name__,
            "evidence_quality": evidence_quality,
        }

    return _build_search_result(
        query=clean_query,
        retrieval_result=retrieval_result,
        expected_source_category=expected_source_category,
    )


def _build_search_result(
    query: str,
    retrieval_result: dict[str, Any],
    expected_source_category: str | None,
) -> dict[str, Any]:
    chunks = _normalize_chunks(retrieval_result.get("chunks", []))
    source_details = _normalize_source_details(retrieval_result.get("sources", []))
    sources = _unique_sources(source_details)
    fallback_used = _resolve_fallback_used(retrieval_result, chunks, source_details)
    retrieval_backend = _resolve_retrieval_backend(chunks, source_details)
    retrieval_type = _resolve_retrieval_type(chunks, source_details)
    evidence_chunks = _build_evidence_chunks(chunks, source_details)
    evidence_quality = evaluate_rag_evidence_quality(
        evidence_chunks=evidence_chunks,
        expected_source_category=expected_source_category,
        fallback_used=fallback_used,
    )

    return {
        "query": query,
        "evidence_chunks": evidence_chunks,
        "sources": sources,
        "source_details": source_details,
        "scores": [chunk.get("score") for chunk in chunks],
        "rerank_scores": [chunk.get("rerank_score") for chunk in chunks],
        "count": len(sources),
        "fallback_used": fallback_used,
        "retrieval_backend": retrieval_backend,
        "retrieval_type": retrieval_type,
        "retrieval_status": "executed_with_hits" if sources else "executed_no_hit",
        "evidence_quality": evidence_quality,
    }


def _validate_query(query: str) -> str:
    if not isinstance(query, str):
        raise TypeError("query must be a string.")
    clean_query = query.strip()
    if not clean_query:
        raise ValueError("query must not be empty.")
    return clean_query


def _validate_top_k(top_k: int) -> int:
    if isinstance(top_k, bool) or not isinstance(top_k, int):
        raise TypeError("top_k must be an integer.")
    if not 1 <= top_k <= 10:
        raise ValueError("top_k must be between 1 and 10.")
    return top_k


def _normalize_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for chunk in chunks or []:
        if not isinstance(chunk, dict):
            continue
        metadata = chunk.get("metadata", {}) if isinstance(chunk.get("metadata"), dict) else {}
        normalized.append(
            {
                "chunk_id": chunk.get("chunk_id"),
                "document_id": metadata.get("document_id"),
                "document_version": metadata.get("document_version"),
                "source": chunk.get("source"),
                "source_category": metadata.get("source_category"),
                "document_status": metadata.get("document_status"),
                "is_enabled": metadata.get("is_enabled"),
                "source_name": metadata.get("source_name") or chunk.get("source") or chunk.get("title"),
                "title": chunk.get("title"),
                "score": chunk.get("score"),
                "rerank_score": chunk.get("rerank_score"),
                "retrieval_backend": metadata.get("retrieval_backend"),
                "vector_backend": metadata.get("vector_backend"),
                "pgvector_fallback_used": metadata.get("pgvector_fallback_used", False),
                "fallback_used": metadata.get("retrieval_fallback", False),
                "retrieval_type": metadata.get("retrieval_type"),
                "rerank_enabled": metadata.get("rerank_enabled"),
                "text_preview": str(chunk.get("text", ""))[:120],
            }
        )
    return normalized


def _normalize_source_details(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_details = []
    seen = set()
    for source in sources or []:
        if not isinstance(source, dict) or not source.get("source"):
            continue
        source_name = str(source["source"])
        if source_name in seen:
            continue
        seen.add(source_name)
        source_details.append(
            {
                "source": source_name,
                "title": source.get("title"),
                "document_id": source.get("document_id"),
                "document_version": source.get("document_version"),
                "chunk_id": source.get("chunk_id"),
                "source_category": source.get("source_category"),
                "document_status": source.get("document_status"),
                "is_enabled": source.get("is_enabled"),
                "source_name": source.get("source_name") or source.get("source") or source.get("title"),
                "score": source.get("score"),
                "rerank_score": source.get("rerank_score"),
                "retrieval_backend": source.get("retrieval_backend"),
                "vector_backend": source.get("vector_backend"),
                "pgvector_fallback_used": source.get("pgvector_fallback_used", False),
                "fallback_used": source.get("retrieval_fallback", False),
                "retrieval_type": source.get("retrieval_type"),
                "rerank_enabled": source.get("rerank_enabled"),
            }
        )
    return source_details


def _build_evidence_chunks(
    chunks: list[dict[str, Any]],
    source_details: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if chunks:
        return [
            {
                "chunk_id": chunk.get("chunk_id"),
                "document_id": chunk.get("document_id"),
                "document_version": chunk.get("document_version"),
                "source": chunk.get("source"),
                "source_category": chunk.get("source_category"),
                "document_status": chunk.get("document_status"),
                "is_enabled": chunk.get("is_enabled"),
                "source_name": chunk.get("source_name"),
                "score": chunk.get("score"),
                "rerank_score": chunk.get("rerank_score"),
                "retrieval_backend": chunk.get("retrieval_backend"),
                "vector_backend": chunk.get("vector_backend"),
                "pgvector_fallback_used": chunk.get("pgvector_fallback_used", False),
                "text_preview": str(chunk.get("text_preview", ""))[:200],
            }
            for chunk in chunks
        ]

    return [
        {
            "chunk_id": source.get("chunk_id"),
            "document_id": source.get("document_id"),
            "document_version": source.get("document_version"),
            "source": source.get("source"),
            "source_category": source.get("source_category"),
            "document_status": source.get("document_status"),
            "is_enabled": source.get("is_enabled"),
            "source_name": source.get("source_name"),
            "score": source.get("score"),
            "rerank_score": source.get("rerank_score"),
            "retrieval_backend": source.get("retrieval_backend"),
            "vector_backend": source.get("vector_backend"),
            "pgvector_fallback_used": source.get("pgvector_fallback_used", False),
            "text_preview": "",
        }
        for source in source_details
    ]


def _unique_sources(source_details: list[dict[str, Any]]) -> list[str]:
    return [source["source"] for source in source_details if source.get("source")]


def _resolve_fallback_used(
    retrieval_result: dict[str, Any],
    chunks: list[dict[str, Any]],
    source_details: list[dict[str, Any]],
) -> bool:
    if retrieval_result.get("fallback_used"):
        return True
    return any(row.get("fallback_used") for row in chunks + source_details)


def _resolve_retrieval_backend(
    chunks: list[dict[str, Any]],
    source_details: list[dict[str, Any]],
) -> str:
    rows = chunks or source_details
    for row in rows:
        backend = row.get("retrieval_backend")
        if backend:
            return str(backend)
    if any(row.get("document_id") or row.get("document_version") for row in rows):
        return "db"
    if rows:
        return "markdown"
    return "none"


def _resolve_retrieval_type(
    chunks: list[dict[str, Any]],
    source_details: list[dict[str, Any]],
) -> str | None:
    for row in chunks + source_details:
        retrieval_type = row.get("retrieval_type")
        if retrieval_type:
            return str(retrieval_type)
    return None
