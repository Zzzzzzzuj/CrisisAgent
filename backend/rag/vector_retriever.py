from pathlib import Path

from backend.rag.base import BaseRetriever
from backend.rag.document_loader import KNOWLEDGE_BASE_DIR, load_chunks
from backend.rag.embedding import EmbeddingModel, get_embedding_model
from backend.rag.pgvector_store import PgVectorStore
from backend.rag.schemas import RetrievalResult
from backend.rag.vector_backend import get_vector_backend
from backend.rag.vector_store import VectorStore


class VectorRetriever(BaseRetriever):
    def __init__(
        self,
        embedding_model: EmbeddingModel | None = None,
        vector_store: VectorStore | None = None,
        pgvector_store: PgVectorStore | None = None,
        knowledge_base_dir: str | Path = KNOWLEDGE_BASE_DIR,
        vector_backend: str | None = None,
    ):
        self.embedding_model = embedding_model or get_embedding_model()
        self.vector_store = vector_store or VectorStore()
        self.pgvector_store = pgvector_store
        self.knowledge_base_dir = knowledge_base_dir
        self.vector_backend = vector_backend or get_vector_backend()
        self._build_index()

    def retrieve(self, query: str, top_k: int = 3) -> RetrievalResult:
        query_embedding = self.embedding_model.embed(query)
        if self.vector_backend == "pgvector":
            try:
                pgvector_store = self.pgvector_store or PgVectorStore()
                return pgvector_store.search(query_embedding, top_k=top_k)
            except Exception:
                fallback_result = self.vector_store.search(query_embedding, top_k=top_k)
                return _mark_pgvector_fallback(fallback_result)
        return self.vector_store.search(query_embedding, top_k=top_k)

    def _build_index(self) -> None:
        chunks = load_chunks(self.knowledge_base_dir)
        vector_chunks = []

        for index, chunk in enumerate(chunks):
            chunk_id = chunk.get("chunk_id") or f"{chunk['source']}#{index}"
            vector_chunks.append(
                {
                    "chunk_id": chunk_id,
                    "text": chunk["text"],
                    "source": chunk["source"],
                    "title": chunk["title"],
                    "embedding": self.embedding_model.embed(chunk["text"]),
                    "metadata": dict(chunk.get("metadata", {})),
                }
            )

        self.vector_store.add(vector_chunks)


def _mark_pgvector_fallback(result: RetrievalResult) -> RetrievalResult:
    chunks = []
    for chunk in result.chunks:
        metadata = dict(chunk.metadata or {})
        metadata.update(
            {
                "retrieval_backend": "json_vector",
                "vector_backend": "json",
                "pgvector_fallback_used": True,
                "retrieval_fallback": True,
            }
        )
        chunks.append(
            type(chunk)(
                chunk_id=chunk.chunk_id,
                text=chunk.text,
                source=chunk.source,
                title=chunk.title,
                score=chunk.score,
                metadata=metadata,
                embedding_score=chunk.embedding_score,
                rerank_score=chunk.rerank_score,
            )
        )
    return RetrievalResult(
        context=result.context,
        chunks=chunks,
        sources=[
            {
                **source,
                "retrieval_backend": "json_vector",
                "vector_backend": "json",
                "pgvector_fallback_used": True,
                "retrieval_fallback": True,
            }
            for source in result.sources
        ],
    )
