from backend.context import ContextManager
from backend.context.schemas import ContextItem


def test_context_manager_adds_context():
    manager = ContextManager()

    item = manager.add_context(
        source="rag",
        content="food safety response guidance",
        priority=10,
    )

    assert isinstance(item, ContextItem)
    assert item.source == "rag"
    assert item.content == "food safety response guidance"
    assert item.priority == 10
    assert item.token_size == 4


def test_context_manager_sorts_by_priority_descending():
    manager = ContextManager()
    manager.add_context("low", "low priority", priority=1)
    manager.add_context("high", "high priority", priority=9)
    manager.add_context("middle", "middle priority", priority=5)

    sorted_items = manager.sort_by_priority()

    assert [item.source for item in sorted_items] == ["high", "middle", "low"]


def test_context_manager_build_context_respects_token_limit():
    manager = ContextManager()
    manager.add_context("high", "alpha beta gamma", priority=10, token_size=3)
    manager.add_context("middle", "delta epsilon", priority=5, token_size=2)
    manager.add_context("low", "zeta eta", priority=1, token_size=2)

    context = manager.build_context(max_tokens=5)

    assert "[high]" in context
    assert "alpha beta gamma" in context
    assert "[middle]" in context
    assert "delta epsilon" in context
    assert "[low]" not in context


def test_context_manager_skips_item_larger_than_token_limit():
    manager = ContextManager()
    manager.add_context("too-large", "alpha beta gamma", priority=10, token_size=3)
    manager.add_context("small", "delta", priority=1, token_size=1)

    context = manager.build_context(max_tokens=2)

    assert "[too-large]" not in context
    assert "[small]" in context


def test_context_manager_empty_context_returns_empty_string():
    manager = ContextManager()

    assert manager.build_context(max_tokens=10) == ""
    assert manager.sort_by_priority() == []


def test_context_manager_non_positive_token_limit_returns_empty_string():
    manager = ContextManager()
    manager.add_context("rag", "food safety", priority=10)

    assert manager.build_context(max_tokens=0) == ""
