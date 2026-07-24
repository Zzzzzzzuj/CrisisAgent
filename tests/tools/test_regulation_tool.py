from backend.tools.regulation_tool import RegulationSearchTool


def test_regulation_tool_can_execute():
    tool = RegulationSearchTool()

    result = tool.run({"query": "食品安全 过期原料 监管", "top_k": 3})

    assert "context" in result
    assert "sources" in result
    assert "chunks" in result
    assert result["context"]


def test_regulation_tool_output_structure_is_retrieval_result_compatible():
    tool = RegulationSearchTool()

    result = tool.run({"query": "避免提前定责 条件式责任表达"})

    assert set(result.keys()) == {"context", "chunks", "sources"}
    assert isinstance(result["context"], str)
    assert isinstance(result["chunks"], list)
    assert isinstance(result["sources"], list)


def test_regulation_tool_hits_knowledge_base():
    tool = RegulationSearchTool()

    result = tool.run({"query": "食品品牌使用过期原料，监管介入", "top_k": 3})
    sources = [source["source"] for source in result["sources"]]

    assert "food_safety.md" in sources


def test_regulation_tool_rejects_invalid_params():
    tool = RegulationSearchTool()

    try:
        tool.run({"query": ""})
    except ValueError as exc:
        assert "query" in str(exc)
    else:
        raise AssertionError("Expected invalid query to fail.")
