from dataclasses import dataclass
from html.parser import HTMLParser
import re


@dataclass(frozen=True)
class ExtractedArticle:
    title: str
    content: str
    published_at: str = ""
    extraction_method: str = "fallback"


class _FallbackParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self._in_title = False
        self._ignored_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "title":
            self._in_title = True
        if tag.lower() in {"script", "style", "noscript"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self._in_title = False
        if tag.lower() in {"script", "style", "noscript"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data):
        if self._ignored_depth:
            return
        value = " ".join(str(data).split())
        if not value:
            return
        if self._in_title:
            self.title_parts.append(value)
        self.text_parts.append(value)


def extract_article(html: str, url: str = "") -> ExtractedArticle:
    try:
        import trafilatura  # type: ignore

        content = trafilatura.extract(html, url=url, include_comments=False, include_tables=False) or ""
        metadata = trafilatura.extract_metadata(html) if content else None
        title = (metadata.title if metadata and metadata.title else "").strip()
        if content.strip():
            return ExtractedArticle(title=title, content=content.strip(), published_at="", extraction_method="trafilatura")
    except ImportError:
        pass
    except Exception:
        pass

    parser = _FallbackParser()
    parser.feed(html)
    title = " ".join(parser.title_parts).strip()
    content = " ".join(parser.text_parts).strip()
    content = re.sub(r"\s+", " ", content)
    return ExtractedArticle(title=title, content=content, extraction_method="html_fallback")
