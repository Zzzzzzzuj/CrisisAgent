import hashlib
import re

from .schemas import NormalizedSentimentItem, RawSentimentItem


_HTML_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")
_REPEATED_PUNCT = re.compile(r"([，。！？!?；;、])\1+")


def clean_text(value: str) -> str:
    text = _HTML_TAG.sub(" ", str(value or ""))
    text = _SPACE.sub(" ", text).strip()
    return _REPEATED_PUNCT.sub(r"\1", text)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_item(item: RawSentimentItem) -> NormalizedSentimentItem:
    title = clean_text(item.title)
    content = clean_text(item.content)
    normalized_text = " ".join(part for part in (title, content) if part)
    return NormalizedSentimentItem(
        item_id=item.item_id,
        source_name=clean_text(item.source_name),
        source_url=clean_text(item.source_url),
        title=title,
        normalized_text=normalized_text,
        published_at=clean_text(item.published_at),
        company=clean_text(item.company),
        fact_status=item.fact_status if item.fact_status in {"verified", "unverified", "conflicting"} else "unverified",
        url_hash=_sha256(clean_text(item.source_url)),
        title_hash=_sha256(title.lower()),
        content_hash=_sha256(content.lower()),
    )
