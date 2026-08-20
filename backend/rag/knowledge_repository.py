import hashlib
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from backend.db.models import KnowledgeChunkRecord, KnowledgeDocumentRecord
from backend.db.session import get_session_factory, is_database_checkpoint_enabled
from backend.rag.chunk_strategy import split_markdown_documents
from backend.rag.embedding import get_embedding_model
from backend.rag.pgvector_store import upsert_pgvector_embedding
from backend.rag.vector_backend import is_pgvector_backend_enabled


PUBLISHED = "published"
EMBEDDED = "embedded"


class KnowledgeRepository:
    def __init__(self, session_factory: sessionmaker | None = None):
        self.session_factory = session_factory or get_session_factory()

    def ingest_file(
        self,
        path: str | Path,
        source_category: str = "general",
        publish: bool = True,
        embedding_model_name: str | None = None,
    ) -> dict:
        file_path = Path(path)
        content = file_path.read_text(encoding="utf-8").strip()
        source = file_path.name
        title = _extract_title(content, file_path.stem)
        document_id = _document_id(source)
        content_hash = _content_hash(content)
        embedding_model = get_embedding_model(embedding_model_name)
        documents = [
            {
                "source": source,
                "title": title,
                "content": content,
            }
        ]
        chunks = split_markdown_documents(documents)

        with self.session_factory() as db:
            existing = db.execute(
                select(KnowledgeDocumentRecord)
                .where(KnowledgeDocumentRecord.document_id == document_id)
                .order_by(KnowledgeDocumentRecord.version.desc())
            ).scalars().first()
            version = (existing.version + 1) if existing and existing.content_hash != content_hash else (existing.version if existing else 1)

            db.execute(delete(KnowledgeChunkRecord).where(KnowledgeChunkRecord.document_id == document_id))
            if existing is None:
                existing = KnowledgeDocumentRecord(document_id=document_id)
                db.add(existing)

            existing.source = source
            existing.title = title
            existing.source_category = source_category
            existing.version = version
            existing.content_hash = content_hash
            existing.content = content
            existing.published_status = PUBLISHED if publish else "draft"
            existing.embedding_status = EMBEDDED if chunks else "empty"

            chunk_rows = []
            for index, chunk in enumerate(chunks):
                embedding = embedding_model.embed(chunk["text"])
                chunk_id = f"{document_id}:v{version}:chunk-{index}"
                metadata = dict(chunk.get("metadata", {}))
                metadata.update(
                    {
                        "document_id": document_id,
                        "document_version": version,
                        "source_category": source_category,
                    }
                )
                row = KnowledgeChunkRecord(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    document_version=version,
                    source=source,
                    title=title,
                    source_category=source_category,
                    chunk_index=index,
                    text=chunk["text"],
                    embedding=embedding,
                    embedding_model=embedding_model.__class__.__name__,
                    embedding_dimension=len(embedding),
                    embedding_status=EMBEDDED,
                    metadata_json=metadata,
                )
                db.add(row)
                chunk_rows.append(row)
                if is_pgvector_backend_enabled():
                    db.flush()
                    try:
                        with db.begin_nested():
                            upsert_pgvector_embedding(
                                db,
                                chunk_id=chunk_id,
                                embedding=embedding,
                                embedding_model=embedding_model.__class__.__name__,
                                embedding_dimension=len(embedding),
                            )
                    except Exception:
                        metadata["pgvector_write_fallback"] = True
                        row.metadata_json = metadata
                        flag_modified(row, "metadata_json")

            db.commit()
            return {
                "document_id": document_id,
                "source": source,
                "title": title,
                "source_category": source_category,
                "version": version,
                "embedding_status": existing.embedding_status,
                "published_status": existing.published_status,
                "chunk_count": len(chunk_rows),
            }

    def list_documents(self) -> list[dict]:
        with self.session_factory() as db:
            rows = db.execute(
                select(KnowledgeDocumentRecord).order_by(KnowledgeDocumentRecord.source)
            ).scalars().all()
            return [_document_row_to_dict(row) for row in rows]

    def load_published_documents(self) -> list[dict]:
        with self.session_factory() as db:
            rows = db.execute(
                select(KnowledgeDocumentRecord)
                .where(KnowledgeDocumentRecord.published_status == PUBLISHED)
                .order_by(KnowledgeDocumentRecord.source)
            ).scalars().all()
            return [_document_row_to_dict(row, include_content=True) for row in rows]

    def load_published_chunks(self) -> list[dict]:
        with self.session_factory() as db:
            rows = db.execute(
                select(KnowledgeChunkRecord)
                .join(KnowledgeDocumentRecord, KnowledgeChunkRecord.document_id == KnowledgeDocumentRecord.document_id)
                .where(KnowledgeDocumentRecord.published_status == PUBLISHED)
                .order_by(KnowledgeChunkRecord.source, KnowledgeChunkRecord.chunk_index)
            ).scalars().all()
            return [_chunk_row_to_dict(row) for row in rows]


def load_published_documents_from_database() -> list[dict]:
    if not is_database_checkpoint_enabled():
        return []
    try:
        return KnowledgeRepository().load_published_documents()
    except Exception:
        return []


def load_published_chunks_from_database() -> list[dict]:
    if not is_database_checkpoint_enabled():
        return []
    try:
        return KnowledgeRepository().load_published_chunks()
    except Exception:
        return []


def _document_row_to_dict(row: KnowledgeDocumentRecord, include_content: bool = False) -> dict:
    data = {
        "document_id": row.document_id,
        "source": row.source,
        "title": row.title,
        "source_category": row.source_category,
        "version": row.version,
        "embedding_status": row.embedding_status,
        "published_status": row.published_status,
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }
    if include_content:
        data["content"] = row.content
    return data


def _chunk_row_to_dict(row: KnowledgeChunkRecord) -> dict:
    metadata = dict(row.metadata_json or {})
    metadata.update(
        {
            "document_id": row.document_id,
            "document_version": row.document_version,
            "source_category": row.source_category,
            "embedding_status": row.embedding_status,
        }
    )
    return {
        "chunk_id": row.chunk_id,
        "document_id": row.document_id,
        "document_version": row.document_version,
        "source": row.source,
        "title": row.title,
        "source_category": row.source_category,
        "chunk_index": row.chunk_index,
        "text": row.text,
        "embedding": list(row.embedding or []),
        "metadata": metadata,
        "embedding_status": row.embedding_status,
    }


def _extract_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped.removeprefix("# ").strip()
    return fallback


def _document_id(source: str) -> str:
    stem = Path(source).stem.lower().replace(" ", "_")
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]
    return f"{stem}-{digest}"


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
