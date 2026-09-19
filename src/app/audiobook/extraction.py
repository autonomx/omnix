"""Versioned source extraction. TTS normalization never runs in this module."""
from __future__ import annotations

import io
import posixpath
import re
import zipfile
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import unquote
from xml.etree import ElementTree as ET

from .hashing import bytes_hash, object_hash, text_hash
from .integrity import validate_revision
from .models import CanonicalChapter, SourceRevision
from .spans import UnicodeDialogueDetector


EXTRACTOR_VERSION = "audiobook-extractor-v1"
MAX_SOURCE_BYTES = 200 * 1024 * 1024
MAX_EPUB_UNCOMPRESSED_BYTES = 500 * 1024 * 1024
_CHAPTER_HEADING = re.compile(r"^(?:#{1,2}\s+.+|chapter\s+(?:\d+|[IVXLCDM]+)\b.*)$", re.IGNORECASE)


class UnsupportedSource(ValueError):
    pass


class _ReadingHTML(HTMLParser):
    _BLOCKS = {"p", "div", "section", "article", "h1", "h2", "h3", "h4", "blockquote", "li"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.suppressed = 0
        self.headings: list[str] = []
        self._heading: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "body":
            self.suppressed = 0
        if tag in {"script", "style", "nav", "head"}:
            self.suppressed += 1
            return
        if self.suppressed:
            return
        if tag in self._BLOCKS and self.parts and not self.parts[-1].endswith("\n"):
            self.parts.append("\n\n")
        if tag == "br":
            self.parts.append("\n")
        if tag in {"h1", "h2", "h3"}:
            self._heading = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "nav", "head"}:
            self.suppressed = max(0, self.suppressed - 1)
            return
        if self.suppressed:
            return
        if tag in {"h1", "h2", "h3"} and self._heading is not None:
            title = "".join(self._heading).strip()
            if title:
                self.headings.append(title)
            self._heading = None
        if tag in self._BLOCKS:
            self.parts.append("\n\n")

    def handle_data(self, data: str) -> None:
        if not self.suppressed:
            self.parts.append(data)
            if self._heading is not None:
                self._heading.append(data)


def _decode_utf8(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError as exc:
        raise UnsupportedSource("source must be valid UTF-8") from exc


def _text_chapters(content: str) -> list[tuple[str, str]]:
    chapters: list[tuple[str, str]] = []
    title = "Opening"
    current: list[str] = []
    for line in content.splitlines(keepends=True):
        stripped = line.strip()
        if _CHAPTER_HEADING.match(stripped) and current:
            chapters.append((title, "".join(current)))
            current = []
        if _CHAPTER_HEADING.match(stripped):
            title = stripped.lstrip("# ") or title
        current.append(line)
    if current:
        chapters.append((title, "".join(current)))
    return chapters


def _epub_chapters(content: bytes) -> tuple[list[tuple[str, str]], dict[str, str], list[str]]:
    chapters: list[tuple[str, str]] = []
    warnings: list[str] = []
    metadata: dict[str, str] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if sum(item.file_size for item in archive.infolist()) > MAX_EPUB_UNCOMPRESSED_BYTES:
                raise UnsupportedSource("EPUB uncompressed content exceeds the supported limit")
            names = set(archive.namelist())
            if "META-INF/encryption.xml" in names:
                raise UnsupportedSource("encrypted EPUB is unsupported")
            container = ET.fromstring(archive.read("META-INF/container.xml"))
            rootfile = container.find(".//{*}rootfile")
            if rootfile is None or not rootfile.get("full-path"):
                raise UnsupportedSource("EPUB container has no package document")
            opf_path = rootfile.attrib["full-path"]
            opf = ET.fromstring(archive.read(opf_path))
            for key in ("title", "creator", "language"):
                node = opf.find(f".//{{*}}metadata/{{*}}{key}")
                if node is not None and node.text:
                    metadata[key] = node.text.strip()
            manifest: dict[str, tuple[str, str, str]] = {}
            for item in opf.findall(".//{*}manifest/{*}item"):
                item_id = item.get("id")
                if item_id:
                    manifest[item_id] = (item.get("href", ""), item.get("media-type", ""), item.get("properties", ""))
            base = str(PurePosixPath(opf_path).parent)
            for spine_item in opf.findall(".//{*}spine/{*}itemref"):
                item = manifest.get(spine_item.get("idref", ""))
                if not item:
                    raise UnsupportedSource("EPUB spine item missing from manifest")
                href, media_type, properties = item
                if "nav" in properties.split() or media_type not in {"application/xhtml+xml", "text/html"}:
                    continue
                path = posixpath.normpath(posixpath.join(base, unquote(href.split("#", 1)[0])))
                if path not in names:
                    raise UnsupportedSource(f"EPUB spine resource missing: {path}")
                parser = _ReadingHTML()
                parser.feed(_decode_utf8(archive.read(path)))
                text = "".join(parser.parts).strip("\n")
                if text.strip():
                    chapters.append((parser.headings[0] if parser.headings else f"Chapter {len(chapters) + 1}", text))
            if not chapters:
                raise UnsupportedSource("EPUB has no readable spine chapters")
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        raise UnsupportedSource("invalid EPUB package") from exc
    return chapters, metadata, warnings


def extract_source(
    *, project_id: str, content: bytes, source_format: str,
    settings: dict[str, object] | None = None,
) -> SourceRevision:
    if source_format not in {"epub", "txt", "md"}:
        raise UnsupportedSource(f"unsupported source format: {source_format}")
    if len(content) > MAX_SOURCE_BYTES:
        raise UnsupportedSource("source exceeds the supported size limit")
    settings = dict(settings or {})
    if settings:
        raise UnsupportedSource("unknown extraction settings")
    if source_format == "epub":
        source_chapters, metadata, warnings = _epub_chapters(content)
    else:
        source_chapters = _text_chapters(_decode_utf8(content))
        metadata, warnings = {}, []
    if not source_chapters or not any(text.strip() for _, text in source_chapters):
        raise UnsupportedSource("source has no readable text")
    original_hash = bytes_hash(content)
    settings_hash = object_hash(settings)
    chapter_hashes = [text_hash(text) for _, text in source_chapters]
    canonical_hash = object_hash({
        "extractor_version": EXTRACTOR_VERSION,
        "settings_hash": settings_hash,
        "original_asset_hash": original_hash,
        "chapters": chapter_hashes,
    })
    revision_id = f"ab:sr:{text_hash(f'{project_id}:{canonical_hash}') }"
    detector = UnicodeDialogueDetector()
    chapters = tuple(
        CanonicalChapter(
            id=f"ab:ch:{text_hash(f'{revision_id}:{ordinal}:{chapter_hashes[ordinal]}')}",
            ordinal=ordinal,
            title=title,
            canonical_text=text,
            canonical_hash=chapter_hashes[ordinal],
            spans=(),
            structure={"source_format": source_format},
        )
        for ordinal, (title, text) in enumerate(source_chapters)
    )
    chapters = tuple(
        CanonicalChapter(
            id=chapter.id, ordinal=chapter.ordinal, title=chapter.title,
            canonical_text=chapter.canonical_text, canonical_hash=chapter.canonical_hash,
            spans=detector.detect(chapter.id, chapter.canonical_text), structure=chapter.structure,
        )
        for chapter in chapters
    )
    revision = SourceRevision(
        id=revision_id, project_id=project_id,
        original_asset_hash=original_hash, source_format=source_format,
        extractor_version=EXTRACTOR_VERSION, extraction_settings=settings,
        extraction_settings_hash=settings_hash, canonical_hash=canonical_hash,
        chapters=chapters, metadata=metadata, warnings=tuple(warnings),
    )
    validate_revision(revision)
    return revision
