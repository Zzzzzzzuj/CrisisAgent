from backend.rag.document_loader import load_documents
from backend.rag.retriever import retrieve
from backend.rag.text_splitter import split_documents


def test_load_documents_reads_knowledge_base():
    documents = load_documents()

    sources = {document["source"] for document in documents}
    assert "food_safety.md" in sources
    assert "crisis_response.md" in sources
    assert "legal_risk_rules.md" in sources
    assert all(document["title"] for document in documents)
    assert all(document["content"] for document in documents)


def test_split_documents_keeps_source_metadata():
    documents = load_documents()
    chunks = split_documents(documents)

    assert chunks
    assert all("text" in chunk for chunk in chunks)
    assert all("source" in chunk for chunk in chunks)
    assert all("title" in chunk for chunk in chunks)
    assert any(chunk["source"] == "food_safety.md" for chunk in chunks)


def test_food_safety_query_hits_food_safety_source():
    result = retrieve("食品品牌使用过期原料，监管要求介入调查", top_k=3)

    sources = [item["source"] for item in result["sources"]]
    assert "food_safety.md" in sources
    assert result["context"]


def test_avoid_premature_liability_query_hits_legal_rules_source():
    result = retrieve("避免提前定责，不要确认违法，使用条件式责任表达", top_k=3)

    sources = [item["source"] for item in result["sources"]]
    assert "legal_risk_rules.md" in sources
    assert result["context"]
