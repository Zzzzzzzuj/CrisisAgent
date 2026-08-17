from pathlib import Path

from backend.rag.base import BaseRetriever
from backend.rag.document_loader import KNOWLEDGE_BASE_DIR, load_chunks
from backend.rag.embedding import EmbeddingModel, get_embedding_model
from backend.rag.schemas import RetrievalResult
from backend.rag.vector_store import VectorStore


class VectorRetriever(BaseRetriever):
    def __init__(
        self,
        embedding_model: EmbeddingModel | None = None,
        vector_store: VectorStore | None = None,
        knowledge_base_dir: str | Path = KNOWLEDGE_BASE_DIR,
    ):
        self.embedding_model = embedding_model or get_embedding_model()
        self.vector_store = vector_store or VectorStore()
        self.knowledge_base_dir = knowledge_base_dir
        self._build_index()

    def retrieve(self, query: str, top_k: int = 3) -> RetrievalResult:
        query_embedding = self.embedding_model.embed(query)
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
