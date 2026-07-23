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
