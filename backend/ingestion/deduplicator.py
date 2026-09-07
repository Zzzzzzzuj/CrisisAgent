from datetime import datetime

from .schemas import NormalizedSentimentItem


def _published_key(item: NormalizedSentimentItem) -> datetime:
    try:
        return datetime.fromisoformat(item.published_at.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min


def deduplicate_items(items: list[NormalizedSentimentItem]) -> tuple[list[NormalizedSentimentItem], dict]:
    groups: list[NormalizedSentimentItem] = []
    for item in items:
        keys = [item.url_hash, item.title_hash, item.content_hash]
        current_index = next(
            (
                index
                for index, existing in enumerate(groups)
                if existing.company == item.company
                and any(key and key in {existing.url_hash, existing.title_hash, existing.content_hash} for key in keys)
            ),
            None,
        )
        if current_index is None:
            groups.append(item)
        elif (_published_key(item), len(item.normalized_text)) > (
            _published_key(groups[current_index]), len(groups[current_index].normalized_text)
        ):
            groups[current_index] = item
    result = list(groups)
    return result, {"before": len(items), "after": len(result), "removed": len(items) - len(result)}
