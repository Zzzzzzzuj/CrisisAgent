import json

from backend.rag.knowledge_repository import KnowledgeRepository


def main() -> int:
    repository = KnowledgeRepository()
    documents = repository.list_documents()
    rows = [
        {
            "document_id": document.get("document_id"),
            "source_name": document.get("source_name") or document.get("source"),
            "title": document.get("title"),
            "version": document.get("version"),
            "source_category": document.get("source_category"),
            "status": document.get("status") or document.get("published_status"),
            "is_enabled": document.get("is_enabled"),
            "chunk_count": document.get("chunk_count", 0),
            "embedding_status": document.get("embedding_status"),
        }
        for document in documents
    ]
    print(json.dumps({"documents": rows, "count": len(rows)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
