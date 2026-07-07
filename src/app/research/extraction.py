"""Readable-page extraction built on the shared outbound-web policy."""
from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Callable

from .outbound_web import OutboundWebPolicy, OutboundWebResponse

EXTRACTOR_VERSION = "readable-html-v1"
_MAX_EXTRACTED_CHARACTERS = 24_000


@dataclass(slots=True)
class ExtractedPage:
    requested_url: str
    final_url: str
    title: str
    published_at: str | None
    text: str
    content_hash: str
    extractor_version: str
    elapsed_ms: int


class ReadablePageExtractor:
    def __init__(
        self,
        *,
        policy_factory: Callable[[], OutboundWebPolicy] = OutboundWebPolicy,
        max_characters: int = _MAX_EXTRACTED_CHARACTERS,
    ) -> None:
        self.policy_factory = policy_factory
        self.max_characters = max(1000, int(max_characters))

    def extract(self, url: str) -> ExtractedPage:
        response = self.policy_factory().fetch(url)
        text, title, published_at = extract_readable_content(response)
        return ExtractedPage(
            requested_url=url,
            final_url=response.final_url,
            title=title,
            published_at=published_at,
            text=text[: self.max_characters],
            content_hash=hashlib.sha256(response.content).hexdigest(),
            extractor_version=EXTRACTOR_VERSION,
            elapsed_ms=response.elapsed_ms,
        )


class _ReadableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.published_at: str | None = None
        self._ignored_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        if normalized in {"script", "style", "noscript", "svg", "template"}:
            self._ignored_depth += 1
            return
        if normalized == "title":
            self._in_title = True
        if normalized == "meta":
            values = {str(key).lower(): str(value or "") for key, value in attrs}
            key = (values.get("property") or values.get("name") or "").lower()
            if key in {
                "article:published_time",
                "date",
                "datepublished",
                "publishdate",
                "pubdate",
            }:
                self.published_at = values.get("content") or self.published_at
        if normalized in {"p", "br", "li", "article", "section", "h1", "h2", "h3", "h4"}:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized in {"script", "style", "noscript", "svg", "template"}:
            self._ignored_depth = max(0, self._ignored_depth - 1)
            return
        if normalized == "title":
            self._in_title = False
        if normalized in {"p", "li", "article", "section", "h1", "h2", "h3", "h4"}:
            self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        cleaned = " ".join(html.unescape(data).split())
        if not cleaned:
            return
        if self._in_title:
            self.title_parts.append(cleaned)
        else:
            self.text_parts.append(cleaned)


def extract_readable_content(response: OutboundWebResponse) -> tuple[str, str, str | None]:
    decoded = _decode_response(response.content)
    if response.content_type == "text/plain":
        return _normalize_text(decoded), "", None
    parser = _ReadableHTMLParser()
    parser.feed(decoded)
    parser.close()
    title = " ".join(parser.title_parts).strip()
    return _normalize_text(" ".join(parser.text_parts)), title, parser.published_at


def _decode_response(content: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _normalize_text(value: str) -> str:
    lines = []
    for row in re.split(r"[\r\n]+", value):
        cleaned = " ".join(row.split()).strip()
        if cleaned and (not lines or cleaned != lines[-1]):
            lines.append(cleaned)
    return "\n".join(lines)
