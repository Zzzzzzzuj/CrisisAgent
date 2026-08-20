from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from backend.db.session import get_session_factory
from backend.rag.schemas import RetrievalResult, RetrievedChunk
from backend.rag.vector_backend import get_pgvector_distance


class PgVectorStore:
    def __init__(self, session_factory: sessionmaker | None = None):
        self.session_factory = session_factory or get_session_factory()

    def search(self, query_embedding: list[float], top_k: int = 3) -> RetrievalResult:
        if top_k <= 0 or not query_embedding:
            return RetrievalResult(context="", chunks=[], sources=[])

        distance = get_pgvector_distance()
        operator = "<->" if distance == "l2" else "<=>"
        score_expr = (
            f"1.0 / (1.0 + (v.embedding {operator} CAST(:embedding AS vector)))"
            if distance == "l2"
            else f"1.0 - (v.embedding {operator} CAST(:embedding AS vector))"
        )
        order_expr = f"v.embedding {operator} CAST(:embedding AS vector)"
        query = text(
            f"""
            SELECT
                c.chunk_id,
                c.text,
                c.source,
                c.title,
                c.document_id,
                c.document_version,
                c.source_category,
                c.metadata,
                {score_expr} AS score
            FROM knowledge_chunk_vectors AS v
            JOIN knowledge_chunks AS c ON c.chunk_id = v.chunk_id
            JOIN knowledge_documents AS d ON d.document_id = c.document_id
            WHERE d.published_status = 'published'
            ORDER BY {order_expr} ASC
            LIMIT :top_k
            """
        )

        with self.session_factory() as db:
            rows = db.execute(
                query,
                {
                    "embedding": _format_pgvector(query_embedding),
                    "top_k": top_k,
                },
            ).mappings().all()

        chunks = [_row_to_chunk(row) for row in rows]
        return RetrievalResult(
            context=_format_context(chunks),
            chunks=chunks,
            sources=[
                {
                    "chunk_id": chunk.chunk_id,
                    "source": chunk.source,
                    "title": chunk.title,
                    "score": chunk.score,
                    "document_id": (chunk.metadata or {}).get("document_id"),
                    "document_version": (chunk.metadata or {}).get("document_version"),
                    "source_category": (chunk.metadata or {}).get("source_category"),
                    "retrieval_backend": "pgvector",
                    "vector_backend": "pgvector",
                }
                for chunk in chunks
            ],
        )


def upsert_pgvector_embedding(
    db,
    chunk_id: str,
    embedding: list[float],
    embedding_model: str,
    embedding_dimension: int,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO knowledge_chunk_vectors (
                chunk_id,
                embedding,
                embedding_model,
                embedding_dimension,
                created_at,
                updated_at
            )
            VALUES (
                :chunk_id,
                CAST(:embedding AS vector),
                :embedding_model,
                :embedding_dimension,
                NOW(),
                NOW()
            )
            ON CONFLICT (chunk_id) DO UPDATE SET
                embedding = EXCLUDED.embedding,
                embedding_model = EXCLUDED.embedding_model,
                embedding_dimension = EXCLUDED.embedding_dimension,
                updated_at = NOW()
            """
        ),
        {
            "chunk_id": chunk_id,
            "embedding": _format_pgvector(embedding),
            "embedding_model": embedding_model,
            "embedding_dimension": embedding_dimension,
        },
    )


def _format_pgvector(embedding: list[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in embedding) + "]"


def _row_to_chunk(row: Any) -> RetrievedChunk:
    metadata = dict(row.get("metadata") or {})
    metadata.update(
        {
            "retriever": "vector",
            "retrieval_backend": "pgvector",
            "vector_backend": "pgvector",
            "document_id": row.get("document_id"),
            "document_version": row.get("document_version"),
            "source_category": row.get("source_category"),
        }
    )
    score = round(float(row.get("score") or 0.0), 4)
    return RetrievedChunk(
        chunk_id=row.get("chunk_id"),
        text=row.get("text") or "",
        source=row.get("source") or "",
        title=row.get("title") or "",
        score=score,
        embedding_score=score,
        metadata=metadata,
    )


def _format_context(chunks: list[RetrievedChunk]) -> str:
    context_parts = []
    for chunk in chunks:
        context_parts.append(
            f"[{chunk.source} | chunk_id={chunk.chunk_id} | score={chunk.score}]\n{chunk.text}"
        )
    return "\n\n".join(context_parts)
