import json

from backend.rag.knowledge_repository import KnowledgeRepository


def main() -> int:
    documents = KnowledgeRepository().list_documents()
    print(json.dumps({"documents": documents, "count": len(documents)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
