from backend.rag.schemas import KnowledgeChunk


def split_markdown_documents(
    documents: list[dict],
    chunk_size: int | None = None,
    overlap: int = 0,
) -> list[dict]:
    if chunk_size is not None and chunk_size <= 0:
        raise ValueError("chunk_size must be positive.")
    if overlap < 0:
        raise ValueError("overlap cannot be negative.")
    if chunk_size is not None and overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size.")

    chunks = []
    for document in documents:
        sections = _split_markdown_sections(document["content"])
        for section_index, section in enumerate(sections):
            section_title = _extract_section_title(section) or document["title"]
            section_chunks = _split_text_with_overlap(section, chunk_size, overlap)
            for chunk_index, text in enumerate(section_chunks):
                chunk = KnowledgeChunk(
                    text=text,
                    source=document["source"],
                    title=document["title"],
                ).to_dict()
                chunk["metadata"] = {
                    "document_title": document["title"],
                    "section_title": section_title,
                    "section_index": section_index,
                    "chunk_index": chunk_index,
                    "chunk_size": chunk_size,
                    "overlap": overlap,
                }
                chunks.append(chunk)

    return chunks


def _split_markdown_sections(content: str) -> list[str]:
    sections = []
    current_lines = []

    for line in content.splitlines():
        if line.startswith("## ") and current_lines:
            sections.append("\n".join(current_lines).strip())
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        sections.append("\n".join(current_lines).strip())

    return [section for section in sections if section]


def _extract_section_title(section: str) -> str | None:
    for line in section.splitlines():
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return None


def _split_text_with_overlap(text: str, chunk_size: int | None, overlap: int) -> list[str]:
    if chunk_size is None or len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    step = chunk_size - overlap
    while start < len(text):
        chunk = text[start : start + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
        start += step

    return chunks
