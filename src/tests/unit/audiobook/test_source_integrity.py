from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from io import BytesIO
from random import Random
from zipfile import ZipFile

import pytest

from app.audiobook.extraction import UnsupportedSource, extract_source, parse_page_ranges
from app.audiobook.integrity import SourceIntegrityError, validate_chapter, validate_revision
from app.audiobook.hashing import bytes_hash


def test_public_domain_epub_is_deterministic_and_lossless() -> None:
    fixture = Path(__file__).resolve().parents[2] / "fixtures" / "audiobook" / "yellow_wallpaper_gutenberg_1952.epub"
    content = fixture.read_bytes()
    assert bytes_hash(content) == "bc2c1a73a67f5b62d92ff060a9ca78852d8bf9ace819c45db1d981e1b41f63df"
    first = extract_source(project_id="golden-book", content=content, source_format="epub")
    second = extract_source(project_id="golden-book", content=content, source_format="epub")
    validate_revision(first)
    assert first == second
    assert len(first.chapters) == 2
    assert sum(len(chapter.spans) for chapter in first.chapters) == 44


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


def test_html_source_extracts_visible_text_and_headings() -> None:
    content = b"<html><head><title>Hidden</title></head><body><h1>Chapter 1</h1><p>Visible text.</p><script>ignore()</script></body></html>"
    revision = extract_source(project_id="book:html", content=content, source_format="html")

    assert revision.chapters[0].title == "Chapter 1"
    assert "Visible text." in revision.chapters[0].canonical_text
    assert "ignore" not in revision.chapters[0].canonical_text


def _pdf_with_text() -> bytes:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length 66 >>\nstream\nBT /F1 18 Tf 72 720 Td (Chapter 1) Tj 0 -24 Td (PDF text.) Tj ET\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode())
        output.extend(body)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    output.extend(b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:]))
    output.extend(
        f"trailer\n<< /Root 1 0 R /Size {len(objects) + 1} >>\nstartxref\n{xref_offset}\n%%EOF\n".encode()
    )
    return bytes(output)


def test_pdf_source_extracts_text() -> None:
    pytest.importorskip("PyPDF2")
    revision = extract_source(project_id="book:pdf", content=_pdf_with_text(), source_format="pdf")

    assert "Chapter 1" in revision.chapters[0].canonical_text
    assert "PDF text." in revision.chapters[0].canonical_text


def test_pdf_with_spelled_chapter_numbers_creates_each_chapter() -> None:
    pytest.importorskip("PyPDF2")
    fixture = Path(__file__).resolve().parents[4] / "resources" / "data" / "audiobooks" / "the_gold_cart_merchant.pdf"
    revision = extract_source(
        project_id="book:gold-cart-merchant", content=fixture.read_bytes(), source_format="pdf",
    )

    assert [chapter.title for chapter in revision.chapters] == [
        "Chapter One: The Cart Beyond the Castle",
        "Chapter Two: Daniel's Marvels and Sundries",
        "Chapter Three: The Sale That Saved the Market",
    ]
    assert "THE GOLD CART MERCHANT" in revision.chapters[0].canonical_text


def _pdf_with_pages() -> bytes:
    page_text = ["Title page.", "Chapter 1. Main text.", "References page."]
    page_objects: list[bytes] = []
    for page_number, text in enumerate(page_text):
        content_id = (4, 7, 9)[page_number]
        stream = f"BT /F1 18 Tf 72 720 Td ({text}) Tj ET\n".encode()
        page_objects.extend([
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents {content_id} 0 R >>".encode(),
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream",
        ])
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R 6 0 R 8 0 R] /Count 3 >>",
        page_objects[0], page_objects[1],
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        page_objects[2], page_objects[3], page_objects[4], page_objects[5],
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode())
        output.extend(body)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    output.extend(b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:]))
    output.extend(
        f"trailer\n<< /Root 1 0 R /Size {len(objects) + 1} >>\nstartxref\n{xref_offset}\n%%EOF\n".encode()
    )
    return bytes(output)


def test_pdf_page_exclusions_create_distinct_immutable_revision() -> None:
    pytest.importorskip("PyPDF2")
    content = _pdf_with_pages()
    complete = extract_source(project_id="book:pdf-pages", content=content, source_format="pdf")
    filtered = extract_source(
        project_id="book:pdf-pages", content=content, source_format="pdf",
        settings={"excluded_page_ranges": [[3, 3], [1, 1]]},
    )

    complete_text = "".join(chapter.canonical_text for chapter in complete.chapters)
    filtered_text = "".join(chapter.canonical_text for chapter in filtered.chapters)
    assert "Title page." in complete_text and "References page." in complete_text
    assert "Title page." not in filtered_text
    assert "Chapter 1. Main text." in filtered_text
    assert "References page." not in filtered_text
    assert filtered.extraction_settings == {"excluded_page_ranges": [[1, 1], [3, 3]]}
    assert filtered.warnings == ("Excluded PDF pages: 1, 3",)
    assert filtered.id != complete.id
    assert filtered.original_asset_hash == complete.original_asset_hash


def test_pdf_outline_headings_create_chapters_after_front_matter_exclusion() -> None:
    pdf = pytest.importorskip("PyPDF2")
    writer = pdf.PdfWriter()
    for page in pdf.PdfReader(BytesIO(_pdf_with_pages())).pages:
        writer.add_page(page)
    writer.add_outline_item("Chapter 1. Main text.", 1)
    writer.add_outline_item("References page.", 2)
    output = BytesIO()
    writer.write(output)

    revision = extract_source(
        project_id="book:pdf-outlines", content=output.getvalue(), source_format="pdf",
        settings={"excluded_page_ranges": [[1, 1]]},
    )
    assert [chapter.title for chapter in revision.chapters] == [
        "Chapter 1. Main text.", "References page.",
    ]
    assert all("Title page." not in chapter.canonical_text for chapter in revision.chapters)


def test_pdf_page_exclusions_validate_ranges() -> None:
    assert parse_page_ranges("1-3, 42-45, 2") == [[1, 3], [42, 45]]
    with pytest.raises(UnsupportedSource, match="start at 1"):
        parse_page_ranges("0-2")
    with pytest.raises(UnsupportedSource, match="start at 1"):
        parse_page_ranges("3-1")


def test_pdf_page_exclusions_reject_ranges_past_document() -> None:
    pytest.importorskip("PyPDF2")
    with pytest.raises(UnsupportedSource, match="3 pages"):
        extract_source(
            project_id="book:pdf-pages", content=_pdf_with_pages(), source_format="pdf",
            settings={"excluded_page_ranges": [[4, 4]]},
        )


def test_docx_source_extracts_paragraphs_and_metadata() -> None:
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.core_properties.title = "DOCX Book"
    document.core_properties.author = "A Writer"
    document.add_heading("Chapter 1", level=1)
    document.add_paragraph("DOCX text.")
    content = BytesIO()
    document.save(content)

    revision = extract_source(project_id="book:docx", content=content.getvalue(), source_format="docx")

    assert revision.metadata == {"title": "DOCX Book", "creator": "A Writer"}
    assert "DOCX text." in revision.chapters[0].canonical_text


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
        validate_chapter(replace(chapter, spans=(chapter.spans[0], chapter.spans[0], *chapter.spans[1:])))
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


def test_seeded_punctuation_streams_are_lossless() -> None:
    random = Random(90317)
    alphabet = 'ABC nita\n\t"“”‘’«»「」—!?.,'
    for _ in range(100):
        sample = "".join(random.choice(alphabet) for _ in range(random.randrange(1, 500)))
        revision = extract_source(project_id="book:property", content=sample.encode(), source_format="txt")
        validate_revision(revision)
        assert "".join(chapter.canonical_text for chapter in revision.chapters) == sample
