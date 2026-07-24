from backend.rag.chunk_strategy import split_markdown_documents


def split_documents(
    documents: list[dict],
    chunk_size: int | None = None,
    overlap: int = 0,
) -> list[dict]:
    return split_markdown_documents(
        documents,
        chunk_size=chunk_size,
        overlap=overlap,
    )
