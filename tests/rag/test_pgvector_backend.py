from pathlib import Path

from backend.rag.pgvector_store import PgVectorStore, _format_pgvector
from backend.rag.schemas import RetrievalResult, RetrievedChunk
from backend.rag.vector_backend import (
    get_pgvector_distance,
    get_pgvector_index_type,
    get_vector_backend,
)
from backend.rag.vector_retriever import VectorRetriever


class TinyEmbeddingModel:
    def embed(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0] if text else [0.0, 0.0, 0.0]


class FailingPgVectorStore:
    def search(self, query_embedding: list[float], top_k: int = 3) -> RetrievalResult:
        raise RuntimeError("pgvector unavailable")


class StubPgVectorStore:
    def __init__(self):
        self.calls = 0

    def search(self, query_embedding: list[float], top_k: int = 3) -> RetrievalResult:
        self.calls += 1
        chunk = RetrievedChunk(
            chunk_id="db-doc:v1:chunk-0",
            text="数据库向量检索结果。",
            source="data_privacy.md",
            title="Data Privacy",
            score=0.91,
            embedding_score=0.91,
            metadata={
                "retriever": "vector",
                "retrieval_backend": "pgvector",
                "vector_backend": "pgvector",
                "document_id": "db-doc",
                "document_version": 1,
                "source_category": "data_privacy",
            },
        )
        return RetrievalResult(
            context="db context",
            chunks=[chunk],
            sources=[
                {
                    "chunk_id": chunk.chunk_id,
                    "source": chunk.source,
                    "title": chunk.title,
                    "score": chunk.score,
                    "retrieval_backend": "pgvector",
                    "vector_backend": "pgvector",
                    "document_id": "db-doc",
                    "document_version": 1,
                    "source_category": "data_privacy",
                }
            ],
        )


def test_vector_backend_defaults_to_json(monkeypatch):
    monkeypatch.delenv("VECTOR_BACKEND", raising=False)

    assert get_vector_backend() == "json"


def test_vector_backend_invalid_value_falls_back_to_json(monkeypatch):
    monkeypatch.setenv("VECTOR_BACKEND", "unknown")

    assert get_vector_backend() == "json"


def test_pgvector_config_parsing(monkeypatch):
    monkeypatch.setenv("VECTOR_BACKEND", "pgvector")
    monkeypatch.setenv("PGVECTOR_INDEX_TYPE", "hnsw")
    monkeypatch.setenv("PGVECTOR_DISTANCE", "l2")

    assert get_vector_backend() == "pgvector"
    assert get_pgvector_index_type() == "hnsw"
    assert get_pgvector_distance() == "l2"


def test_pgvector_literal_format_is_stable():
    assert _format_pgvector([1, 0.5, -0.25]) == "[1.0,0.5,-0.25]"


def test_vector_retriever_uses_pgvector_backend_when_configured(tmp_path):
    knowledge_dir = _write_knowledge_base(tmp_path)
    store = StubPgVectorStore()
    retriever = VectorRetriever(
        embedding_model=TinyEmbeddingModel(),
        pgvector_store=store,
        knowledge_base_dir=knowledge_dir,
        vector_backend="pgvector",
    )

    result = retriever.retrieve("隐私事件", top_k=1)

    assert store.calls == 1
    assert result.sources[0]["retrieval_backend"] == "pgvector"
    assert result.chunks[0].metadata["vector_backend"] == "pgvector"


def test_pgvector_unavailable_falls_back_to_json_vector_store(tmp_path):
    knowledge_dir = _write_knowledge_base(tmp_path)
    retriever = VectorRetriever(
        embedding_model=TinyEmbeddingModel(),
        pgvector_store=FailingPgVectorStore(),
        knowledge_base_dir=knowledge_dir,
        vector_backend="pgvector",
    )

    result = retriever.retrieve("食品安全", top_k=1)

    assert result.chunks
    assert result.sources[0]["retrieval_backend"] == "json_vector"
    assert result.sources[0]["pgvector_fallback_used"] is True
    assert result.chunks[0].metadata["retrieval_fallback"] is True


def test_json_backend_does_not_initialize_pgvector_store(tmp_path):
    knowledge_dir = _write_knowledge_base(tmp_path)
    retriever = VectorRetriever(
        embedding_model=TinyEmbeddingModel(),
        knowledge_base_dir=knowledge_dir,
        vector_backend="json",
    )

    result = retriever.retrieve("食品安全", top_k=1)

    assert isinstance(result, RetrievalResult)
    assert result.sources[0]["retrieval_backend"] == "json_vector"


def _write_knowledge_base(tmp_path: Path) -> Path:
    path = tmp_path / "knowledge"
    path.mkdir()
    (path / "food_safety.md").write_text(
        "# Food Safety\n\n## 核查\n食品安全、过期原料和监管沟通。",
        encoding="utf-8",
    )
    return path
