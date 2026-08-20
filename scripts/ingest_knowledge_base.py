import argparse
import json
import os
from pathlib import Path

from backend.rag.document_loader import KNOWLEDGE_BASE_DIR
from backend.rag.knowledge_repository import KnowledgeRepository


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest local knowledge documents into the database.")
    parser.add_argument(
        "--path",
        default=str(KNOWLEDGE_BASE_DIR),
        help="Markdown/txt file or directory to ingest.",
    )
    parser.add_argument("--category", default="general", help="Default source category.")
    parser.add_argument("--source-category", default=None, help="Default source category alias.")
    parser.add_argument("--draft", action="store_true", help="Ingest as draft instead of published.")
    parser.add_argument(
        "--status",
        choices=("draft", "published", "disabled"),
        default=os.getenv("KNOWLEDGE_DEFAULT_STATUS", None),
        help="Knowledge document governance status.",
    )
    parser.add_argument(
        "--enabled",
        choices=("true", "false"),
        default=os.getenv("KNOWLEDGE_DEFAULT_ENABLED", "true"),
        help="Whether the document is enabled for retrieval.",
    )
    parser.add_argument("--version", type=int, default=None, help="Optional explicit document version.")
    parser.add_argument("--embedding-model", default=None, help="Optional embedding model name.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    paths = _resolve_paths(Path(args.path))
    repository = KnowledgeRepository()
    default_category = args.source_category or args.category
    results = [
        repository.ingest_file(
            path,
            source_category=_infer_category(path, default_category),
            publish=not args.draft,
            embedding_model_name=args.embedding_model,
            status=args.status or ("draft" if args.draft else "published"),
            enabled=args.enabled.lower() == "true",
            version=args.version,
        )
        for path in paths
    ]
    print(json.dumps({"ingested": results, "count": len(results)}, ensure_ascii=False, indent=2))
    return 0


def _resolve_paths(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted([item for item in path.iterdir() if item.suffix.lower() in {".md", ".txt"}])


def _infer_category(path: Path, default: str) -> str:
    name = path.stem.lower()
    for category in (
        "food_safety",
        "data_privacy",
        "service_outage",
        "product_quality",
        "executive_misconduct",
        "legal_risk",
        "crisis_response",
    ):
        if category in name:
            return category
    return default


if __name__ == "__main__":
    raise SystemExit(main())
