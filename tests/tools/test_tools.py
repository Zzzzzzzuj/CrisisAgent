from backend.tools.base import BaseTool
from backend.tools.registry import ToolRegistry


class DummyTool(BaseTool):
    name = "dummy_tool"
    description = "A dummy tool for tests."

    def run(self, params: dict) -> dict:
        return {"echo": params}


def test_tool_can_register():
    registry = ToolRegistry()
    tool = DummyTool()

    registry.register(tool)

    assert registry.list_tools() == [
        {
            "name": "dummy_tool",
            "description": "A dummy tool for tests.",
        }
    ]


def test_tool_can_get_by_name():
    registry = ToolRegistry()
    tool = DummyTool()
    registry.register(tool)

    resolved = registry.get("dummy_tool")

    assert resolved is tool
    assert resolved.run({"value": 1}) == {"echo": {"value": 1}}


def test_tool_interface_matches_contract():
    tool = DummyTool()

    assert isinstance(tool.name, str)
    assert isinstance(tool.description, str)
    assert callable(tool.run)
    assert isinstance(tool.run({}), dict)


def test_duplicate_tool_registration_raises_clear_error():
    registry = ToolRegistry()
    registry.register(DummyTool())

    try:
        registry.register(DummyTool())
    except ValueError as exc:
        assert "Tool already registered" in str(exc)
    else:
        raise AssertionError("Expected duplicate registration to fail.")


def test_missing_tool_raises_clear_error():
    registry = ToolRegistry()

    try:
        registry.get("missing_tool")
    except KeyError as exc:
        assert "Tool not found" in str(exc)
    else:
        raise AssertionError("Expected missing tool lookup to fail.")
