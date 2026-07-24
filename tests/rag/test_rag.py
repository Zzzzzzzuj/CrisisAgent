from backend.rag.document_loader import load_documents
from backend.rag.factory import get_retriever
from backend.rag.keyword_retriever import KeywordRetriever
from backend.rag.retriever import retrieve
from backend.rag.schemas import RetrievalResult
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


def test_keyword_retriever_food_safety_query_hits_food_safety_source():
    result = KeywordRetriever().retrieve("食品品牌使用过期原料，监管要求介入调查", top_k=3)

    sources = [item["source"] for item in result.sources]
    assert isinstance(result, RetrievalResult)
    assert "food_safety.md" in sources
    assert result.context


def test_keyword_retriever_legal_risk_query_hits_legal_rules_source():
    result = KeywordRetriever().retrieve("避免提前定责，不要确认违法，使用条件式责任表达", top_k=3)

    sources = [item["source"] for item in result.sources]
    assert "legal_risk_rules.md" in sources
    assert result.context
    assert result.chunks


def test_legacy_retrieve_entrypoint_returns_compatible_dict():
    result = retrieve("食品安全 危机回应 监管", top_k=3)

    assert "context" in result
    assert "sources" in result
    assert "chunks" in result
    assert isinstance(result["context"], str)
    assert isinstance(result["sources"], list)
    assert isinstance(result["chunks"], list)


def test_factory_returns_keyword_retriever_by_default():
    retriever = get_retriever()

    assert isinstance(retriever, KeywordRetriever)
