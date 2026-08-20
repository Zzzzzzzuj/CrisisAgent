from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from backend.agents import legal_agent
from backend.db.session import Base
from backend.rag.document_loader import load_documents
from backend.rag.knowledge_repository import KnowledgeRepository


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def test_knowledge_document_ingestion_creates_document_and_chunks(tmp_path, session_factory):
    path = _write_markdown(tmp_path)
    repository = KnowledgeRepository(session_factory=session_factory)

    result = repository.ingest_file(path, source_category="data_privacy")
    documents = repository.list_documents()
    chunks = repository.load_published_chunks()

    assert result["source"] == "data_privacy.md"
    assert result["version"] == 1
    assert result["status"] == "published"
    assert result["is_enabled"] is True
    assert result["published_status"] == "published"
    assert result["embedding_status"] == "embedded"
    assert result["chunk_count"] >= 1
    assert documents[0]["source_category"] == "data_privacy"
    assert documents[0]["source_name"] == "data_privacy.md"
    assert documents[0]["status"] == "published"
    assert documents[0]["is_enabled"] is True
    assert documents[0]["chunk_count"] >= 1
    assert chunks[0]["document_id"] == result["document_id"]
    assert chunks[0]["document_version"] == 1
    assert chunks[0]["source_category"] == "data_privacy"
    assert chunks[0]["embedding_status"] == "embedded"
    assert isinstance(chunks[0]["embedding"], list)
    assert chunks[0]["metadata"]["document_status"] == "published"
    assert chunks[0]["metadata"]["is_enabled"] is True
    assert chunks[0]["metadata"]["source_name"] == "data_privacy.md"


def test_knowledge_ingestion_bumps_version_when_content_changes(tmp_path, session_factory):
    path = _write_markdown(tmp_path, body="## 初步响应\n第一版内容。")
    repository = KnowledgeRepository(session_factory=session_factory)

    first = repository.ingest_file(path, source_category="data_privacy")
    path.write_text("# Data Privacy\n\n## 初步响应\n第二版内容。", encoding="utf-8")
    second = repository.ingest_file(path, source_category="data_privacy")

    assert first["document_id"] == second["document_id"]
    assert second["version"] == 2
    chunks = repository.load_published_chunks()
    assert all(chunk["document_version"] == 2 for chunk in chunks)


def test_markdown_fallback_still_loads_when_database_storage_is_disabled(monkeypatch, tmp_path):
    path = _write_markdown(tmp_path)
    monkeypatch.setenv("CHECKPOINT_STORAGE", "json")

    documents = load_documents(tmp_path)

    assert documents
    assert documents[0]["source"] == "data_privacy.md"
    assert documents[0]["content"].startswith("# Data Privacy")
    assert documents[0]["status"] == "published"
    assert documents[0]["is_enabled"] is True
    assert documents[0]["retrieval_fallback"] is True


def test_draft_document_is_not_loaded_for_rag(tmp_path, session_factory):
    path = _write_markdown(tmp_path)
    repository = KnowledgeRepository(session_factory=session_factory)

    repository.ingest_file(path, source_category="data_privacy", status="draft")

    assert repository.load_published_documents() == []
    assert repository.load_published_chunks() == []


def test_disabled_document_is_not_loaded_for_rag(tmp_path, session_factory):
    path = _write_markdown(tmp_path)
    repository = KnowledgeRepository(session_factory=session_factory)

    repository.ingest_file(path, source_category="data_privacy", status="published", enabled=False)

    assert repository.load_published_documents() == []
    assert repository.load_published_chunks() == []


def test_pgvector_ingestion_failure_keeps_json_embedding_fallback(monkeypatch, tmp_path, session_factory):
    path = _write_markdown(tmp_path)
    repository = KnowledgeRepository(session_factory=session_factory)
    monkeypatch.setenv("VECTOR_BACKEND", "pgvector")
    monkeypatch.setattr(
        "backend.rag.knowledge_repository.upsert_pgvector_embedding",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("pgvector unavailable")),
    )

    result = repository.ingest_file(path, source_category="data_privacy")
    chunks = repository.load_published_chunks()

    assert result["chunk_count"] >= 1
    assert chunks[0]["embedding"]
    assert chunks[0]["metadata"]["pgvector_write_fallback"] is True


def test_legal_rag_trace_records_database_chunk_metadata(monkeypatch):
    retrieval_result = {
        "context": "privacy context",
        "sources": [
            {
                "source": "data_privacy.md",
                "title": "Data Privacy",
                "score": 0.8,
                "rerank_score": 0.7,
                "document_id": "data_privacy-abc",
                "document_version": 3,
                "source_category": "data_privacy",
                "document_status": "published",
                "is_enabled": True,
                "source_name": "data_privacy.md",
            }
        ],
        "chunks": [
            {
                "chunk_id": "data_privacy-abc:v3:chunk-0",
                "source": "data_privacy.md",
                "title": "Data Privacy",
                "text": "用户个人信息泄露响应规范。",
                "score": 0.8,
                "rerank_score": 0.7,
                "metadata": {
                    "document_id": "data_privacy-abc",
                    "document_version": 3,
                    "source_category": "data_privacy",
                    "document_status": "published",
                    "is_enabled": True,
                    "source_name": "data_privacy.md",
                    "retrieval_fallback": False,
                },
            }
        ],
    }
    monkeypatch.setattr(
        legal_agent,
        "evaluate_retrieval_need",
        lambda **kwargs: {"need_rag": True, "intent": "crisis_response_needed"},
    )
    monkeypatch.setattr(legal_agent, "retrieve", lambda query, top_k=3: retrieval_result)

    context = legal_agent._retrieve_legal_context(_legal_payload())
    rag_info = legal_agent.get_last_rag_info()

    assert context == "privacy context"
    assert rag_info["hit"] is True
    chunk = rag_info["chunks"][0]
    source_detail = rag_info["source_details"][0]
    assert chunk["chunk_id"] == "data_privacy-abc:v3:chunk-0"
    assert chunk["document_id"] == "data_privacy-abc"
    assert chunk["document_version"] == 3
    assert chunk["source_category"] == "data_privacy"
    assert chunk["document_status"] == "published"
    assert chunk["is_enabled"] is True
    assert chunk["source_name"] == "data_privacy.md"
    assert chunk["retrieval_query"].startswith("事件：")
    assert chunk["fallback_used"] is False
    assert source_detail["document_id"] == "data_privacy-abc"
    assert source_detail["document_version"] == 3
    assert source_detail["source_category"] == "data_privacy"
    assert source_detail["document_status"] == "published"
    assert source_detail["is_enabled"] is True
    assert source_detail["source_name"] == "data_privacy.md"


def _write_markdown(tmp_path: Path, body: str | None = None) -> Path:
    path = tmp_path / "data_privacy.md"
    path.write_text(
        body
        or "# Data Privacy\n\n## 初步响应\n确认影响范围、排查访问日志并保护用户个人信息。",
        encoding="utf-8",
    )
    return path


def _legal_payload() -> dict:
    return {
        "event": "某APP用户个人信息出现异常访问，用户要求说明。",
        "draft": "我们已启动核查。",
        "redteam_review": {"issues": [], "suggestions": []},
    }
