from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from zipfile import ZipFile

import pytest

from app.audiobook.extraction import UnsupportedSource, extract_source
from app.audiobook.integrity import SourceIntegrityError, validate_chapter, validate_revision


@pytest.mark.parametrize("sample", [
    'She said, "Hello."\nThen left.',
    '“Hello,” she said. ‘Goodbye.’',
    "It's Nita's book. 'Hello,' she said.",
    '« Bonjour » et « au revoir ».',
    '— Where are you?\n— Here.\n',
    '「こんにちは」彼は言った。『はい』',
    'An unbalanced “quote with no closing mark',
    'Nested “outer ‘inner’ outer” words.',
    '\n\nChapter 2\nSecond paragraph.\n',
])
def test_every_typography_case_reconstructs_exactly(sample: str) -> None:
    revision = extract_source(project_id="book:1", content=sample.encode(), source_format="txt")
    validate_revision(revision)
    assert "".join(chapter.canonical_text for chapter in revision.chapters) == sample
    assert all("".join(span.source_text for span in chapter.spans) == chapter.canonical_text
               for chapter in revision.chapters)


def test_repeated_extraction_has_identical_identities() -> None:
    content = b"Chapter 1\r\nOne.\r\nChapter 2\r\nTwo."
    first = extract_source(project_id="book:1", content=content, source_format="txt")
    second = extract_source(project_id="book:1", content=content, source_format="txt")
    assert first == second
    assert len(first.chapters) == 2


def test_gap_overlap_reordering_and_text_rewrite_are_rejected() -> None:
    revision = extract_source(project_id="book:1", content=b'A "line" follows.', source_format="txt")
    chapter = revision.chapters[0]
    assert len(chapter.spans) >= 2
    changed = replace(chapter.spans[1], start_offset=chapter.spans[1].start_offset + 1)
    with pytest.raises(SourceIntegrityError):
        validate_chapter(replace(chapter, spans=(chapter.spans[0], changed, *chapter.spans[2:])))
    with pytest.raises(SourceIntegrityError):
        validate_chapter(replace(chapter, spans=tuple(reversed(chapter.spans))))
    with pytest.raises(SourceIntegrityError):
        validate_chapter(replace(chapter, canonical_text="rewritten"))


def _epub(*, encrypted: bool = False) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("META-INF/container.xml", '<container><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>')
        archive.writestr("OEBPS/content.opf", '<package><metadata><title>A Book</title><creator>A Writer</creator></metadata><manifest><item id="one" href="one.xhtml" media-type="application/xhtml+xml"/><item id="two" href="two.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="one"/><itemref idref="two"/></spine></package>')
        archive.writestr("OEBPS/one.xhtml", '<html><body><h1>First</h1><p>Hello &amp; goodbye.</p></body></html>')
        archive.writestr("OEBPS/two.xhtml", '<html><body><h1>Second</h1><p>More words.</p></body></html>')
        if encrypted:
            archive.writestr("META-INF/encryption.xml", "<encryption />")
    return buffer.getvalue()


def test_epub_spine_order_and_metadata() -> None:
    revision = extract_source(project_id="book:1", content=_epub(), source_format="epub")
    assert [chapter.title for chapter in revision.chapters] == ["First", "Second"]
    assert revision.metadata["creator"] == "A Writer"
    validate_revision(revision)


def test_encrypted_epub_rejected() -> None:
    with pytest.raises(UnsupportedSource, match="encrypted"):
        extract_source(project_id="book:1", content=_epub(encrypted=True), source_format="epub")
