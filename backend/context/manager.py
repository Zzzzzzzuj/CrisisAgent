import re

from backend.context.schemas import ContextItem


class ContextManager:
    def __init__(self):
        self._items: list[ContextItem] = []

    def add_context(
        self,
        source: str,
        content: str,
        priority: int = 0,
        token_size: int | None = None,
    ) -> ContextItem:
        item = ContextItem(
            source=source,
            content=content,
            priority=priority,
            token_size=token_size if token_size is not None else _estimate_token_size(content),
        )
        self._items.append(item)
        return item

    def sort_by_priority(self) -> list[ContextItem]:
        return sorted(self._items, key=lambda item: item.priority, reverse=True)

    def build_context(self, max_tokens: int) -> str:
        if max_tokens <= 0:
            return ""

        selected = []
        used_tokens = 0
        for item in self.sort_by_priority():
            if item.token_size > max_tokens:
                continue
            if used_tokens + item.token_size > max_tokens:
                continue
            selected.append(f"[{item.source}]\n{item.content}")
            used_tokens += item.token_size

        return "\n\n".join(selected)


def _estimate_token_size(text: str) -> int:
    if not text:
        return 0

    words = re.findall(r"\w+", text)
    if words:
        return len(words)

    return len(text)
