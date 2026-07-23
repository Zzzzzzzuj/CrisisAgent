from backend.rag.schemas import KnowledgeChunk


def split_documents(documents: list[dict]) -> list[dict]:
    chunks = []

    for document in documents:
        sections = _split_markdown_sections(document["content"])
        for section in sections:
            chunk = KnowledgeChunk(
                text=section,
                source=document["source"],
                title=document["title"],
            )
            chunks.append(chunk.to_dict())

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
