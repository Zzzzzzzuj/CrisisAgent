from pathlib import Path

from backend.rag.base import BaseRetriever
from backend.rag.document_loader import KNOWLEDGE_BASE_DIR, load_documents
from backend.rag.embedding import EmbeddingModel, get_embedding_model
from backend.rag.schemas import RetrievalResult
from backend.rag.text_splitter import split_documents
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
        documents = load_documents(self.knowledge_base_dir)
        chunks = split_documents(documents)
        vector_chunks = []

        for index, chunk in enumerate(chunks):
            vector_chunks.append(
                {
                    "chunk_id": f"{chunk['source']}#{index}",
                    "text": chunk["text"],
                    "source": chunk["source"],
                    "title": chunk["title"],
                    "embedding": self.embedding_model.embed(chunk["text"]),
                }
            )

        self.vector_store.add(vector_chunks)
