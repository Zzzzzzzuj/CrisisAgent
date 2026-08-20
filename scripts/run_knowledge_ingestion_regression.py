import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.db.session import Base
from backend.rag.document_loader import load_documents
from backend.rag.knowledge_repository import KnowledgeRepository
from backend.rag.vector_backend import get_vector_backend


def run_regression() -> dict:
    with TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        paths = _write_fixture_docs(tmp_path)
        repository = KnowledgeRepository(session_factory=_sqlite_session_factory())

        published = repository.ingest_file(
            paths["published"],
            source_category="food_safety",
            status="published",
            enabled=True,
            version=2,
        )
        draft = repository.ingest_file(
            paths["draft"],
            source_category="data_privacy",
            status="draft",
            enabled=True,
        )
        disabled = repository.ingest_file(
            paths["disabled"],
            source_category="service_outage",
            status="published",
            enabled=False,
        )

        documents = repository.list_documents()
        retrievable_chunks = repository.load_published_chunks()
        markdown_fallback = _load_markdown_fallback(tmp_path)

        checks = {
            "document_count": len(documents) == 3,
            "chunk_count": len(retrievable_chunks) >= 1,
            "chunk_id_present": all(chunk.get("chunk_id") for chunk in retrievable_chunks),
            "version_present": all(chunk.get("document_version") for chunk in retrievable_chunks),
            "source_category_present": all(chunk.get("source_category") for chunk in retrievable_chunks),
            "status_and_enabled_present": all(
                chunk.get("document_status") == "published" and chunk.get("is_enabled") is True
                for chunk in retrievable_chunks
            ),
            "published_enabled_retrievable": any(chunk.get("document_id") == published["document_id"] for chunk in retrievable_chunks),
            "draft_not_retrievable": all(chunk.get("document_id") != draft["document_id"] for chunk in retrievable_chunks),
            "disabled_not_retrievable": all(chunk.get("document_id") != disabled["document_id"] for chunk in retrievable_chunks),
            "embedding_metadata_present": all(isinstance(chunk.get("embedding"), list) for chunk in retrievable_chunks),
            "json_markdown_fallback_available": bool(markdown_fallback),
        }
        return {
            "status": "pass" if all(checks.values()) else "fail",
            "checks": checks,
            "documents": _document_summary(documents),
            "retrievable_chunk_count": len(retrievable_chunks),
            "vector_backend": get_vector_backend(),
            "pgvector_note": _pgvector_note(),
        }


def main() -> int:
    result = run_regression()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "pass" else 1


def _sqlite_session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def _write_fixture_docs(tmp_path: Path) -> dict[str, Path]:
    fixtures = {
        "published": "# Food Safety\n\n## 核查\n食品安全批次核查、监管沟通和用户通知。",
        "draft": "# Data Privacy Draft\n\n## 草稿\n个人信息事件草稿知识，不应进入检索。",
        "disabled": "# Service Outage Disabled\n\n## 禁用\n服务故障旧知识，不应进入检索。",
    }
    paths = {}
    for name, content in fixtures.items():
        path = tmp_path / f"{name}.md"
        path.write_text(content, encoding="utf-8")
        paths[name] = path
    return paths


def _load_markdown_fallback(tmp_path: Path) -> list[dict]:
    old_storage = os.environ.get("CHECKPOINT_STORAGE")
    os.environ["CHECKPOINT_STORAGE"] = "json"
    try:
        return load_documents(tmp_path)
    finally:
        if old_storage is None:
            os.environ.pop("CHECKPOINT_STORAGE", None)
        else:
            os.environ["CHECKPOINT_STORAGE"] = old_storage


def _document_summary(documents: list[dict]) -> list[dict]:
    return [
        {
            "document_id": document.get("document_id"),
            "source_name": document.get("source_name"),
            "version": document.get("version"),
            "source_category": document.get("source_category"),
            "status": document.get("status"),
            "is_enabled": document.get("is_enabled"),
            "chunk_count": document.get("chunk_count"),
            "embedding_status": document.get("embedding_status"),
        }
        for document in documents
    ]


def _pgvector_note() -> str:
    if get_vector_backend() != "pgvector":
        return "pgvector not required for this offline regression; VECTOR_BACKEND is json."
    return "pgvector is optional; this regression validates metadata and JSON fallback without requiring a real pgvector service."


if __name__ == "__main__":
    raise SystemExit(main())
