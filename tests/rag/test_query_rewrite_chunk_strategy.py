from backend.rag.chunk_strategy import split_markdown_documents
from backend.rag.query_rewriter import rewrite_query
from backend.rag.text_splitter import split_documents


def test_query_rewriter_expands_food_safety_query():
    queries = rewrite_query("某食品品牌被爆使用过期原料，网友要求监管调查")

    assert queries[0] == "某食品品牌被爆使用过期原料，网友要求监管调查"
    assert "食品安全风险" in queries
    assert "危机回应" in queries
    assert "监管调查" in queries
    assert "消费者沟通" in queries
    assert "法律责任表达" in queries


def test_query_rewriter_returns_empty_for_empty_query():
    assert rewrite_query("") == []
    assert rewrite_query("   ") == []


def test_chunk_strategy_preserves_markdown_title_and_metadata():
    documents = [
        {
            "source": "sample.md",
            "title": "Sample Document",
            "content": "# Root Title\n\n## Section A\nAlpha beta gamma.",
        }
    ]

    chunks = split_markdown_documents(documents)

    assert len(chunks) == 2
    assert chunks[0]["source"] == "sample.md"
    assert chunks[0]["title"] == "Sample Document"
    assert chunks[0]["metadata"]["document_title"] == "Sample Document"
    assert chunks[1]["metadata"]["section_title"] == "Section A"
    assert chunks[1]["metadata"]["section_index"] == 1
    assert chunks[1]["metadata"]["chunk_index"] == 0


def test_chunk_strategy_supports_chunk_size_and_overlap():
    documents = [
        {
            "source": "sample.md",
            "title": "Sample Document",
            "content": "abcdefghij",
        }
    ]

    chunks = split_markdown_documents(documents, chunk_size=4, overlap=2)

    assert [chunk["text"] for chunk in chunks] == ["abcd", "cdef", "efgh", "ghij", "ij"]
    assert all(chunk["metadata"]["chunk_size"] == 4 for chunk in chunks)
    assert all(chunk["metadata"]["overlap"] == 2 for chunk in chunks)


def test_text_splitter_keeps_legacy_entrypoint_with_metadata():
    documents = [
        {
            "source": "sample.md",
            "title": "Sample Document",
            "content": "## Section A\nAlpha beta gamma.",
        }
    ]

    chunks = split_documents(documents)

    assert chunks
    assert "text" in chunks[0]
    assert "source" in chunks[0]
    assert "title" in chunks[0]
    assert "metadata" in chunks[0]
