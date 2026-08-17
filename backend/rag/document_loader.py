from pathlib import Path

from backend.rag.schemas import KnowledgeDocument


KNOWLEDGE_BASE_DIR = Path(__file__).resolve().parent / "knowledge_base"


def _extract_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped.removeprefix("# ").strip()
    return fallback


def load_documents(knowledge_base_dir: str | Path = KNOWLEDGE_BASE_DIR) -> list[dict]:
    database_documents = _load_database_documents_if_available()
    if database_documents:
        return database_documents

    base_dir = Path(knowledge_base_dir)
    documents = []

    for path in sorted(base_dir.glob("*.md")):
        content = path.read_text(encoding="utf-8").strip()
        document = KnowledgeDocument(
            source=path.name,
            title=_extract_title(content, path.stem),
            content=content,
        )
        documents.append(document.to_dict())

    return documents


def load_chunks(knowledge_base_dir: str | Path = KNOWLEDGE_BASE_DIR) -> list[dict]:
    database_chunks = _load_database_chunks_if_available()
    if database_chunks:
        return database_chunks

    from backend.rag.text_splitter import split_documents

    return split_documents(load_documents(knowledge_base_dir))


def _load_database_documents_if_available() -> list[dict]:
    try:
        from backend.rag.knowledge_repository import load_published_documents_from_database

        return load_published_documents_from_database()
    except Exception:
        return []


def _load_database_chunks_if_available() -> list[dict]:
    try:
        from backend.rag.knowledge_repository import load_published_chunks_from_database

        return load_published_chunks_from_database()
    except Exception:
        return []
