"""A story as a book file (ST-6.5): EPUB, DOCX or PDF, built from its visible pages.

The book is the manuscript as a reader sees it: the title, then each chapter under its heading, the pages of
a chapter separated by a scene break, and each block as a paragraph. Speaker tags are the writer's working
data and stay out of the book. EPUB and PDF are written with the standard library; DOCX uses python-docx,
which the gateway already installs for Audiobook's DOCX import.
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from typing import Any, Literal
from xml.sax.saxutils import escape

from .contracts import CONTROL_CHARS

ExportFormat = Literal["epub", "docx", "pdf"]

MEDIA_TYPES: dict[str, str] = {
    "epub": "application/epub+zip",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}

SCENE_BREAK = "* * *"


@dataclass
class BookChapter:
    title: str
    # Each scene is one page of the story: its paragraphs in order.
    scenes: list[list[str]] = field(default_factory=list)


@dataclass
class Book:
    identifier: str
    title: str
    modified: str
    chapters: list[BookChapter]


def book_of(project: Any) -> Book:
    """The visible pages of a project (a ``StoryProject``) as chapters of scenes."""
    chapters: list[BookChapter] = []
    current: int | None = None
    title = _clean(project.title) or "Untitled story"
    for page in (page for page in project.pages if not page.hidden):
        paragraphs = [text for text in (_clean(block.text) for block in page.blocks) if text]
        if not paragraphs:
            continue
        if page.chapter != current:
            current = page.chapter
            # A drafted opening page carries the story's own title; the chapter is not headed with it again.
            heading = _clean(page.title)
            if not heading or heading.casefold() == title.casefold():
                heading = f"Chapter {page.chapter}"
            chapters.append(BookChapter(title=heading))
        chapters[-1].scenes.append(paragraphs)
    return Book(identifier=project.id, title=title, modified=_epub_date(project.updated_at), chapters=chapters)


def _clean(text: str) -> str:
    """Text without the control characters an EPUB or DOCX may not hold (a story saved before they were
    refused, or pasted from another document, can still carry them)."""
    return CONTROL_CHARS.sub("", text or "").strip()


def file_name(book: Book, fmt: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", book.title.lower()).strip("-") or "story"
    return f"{slug[:80]}.{fmt}"


def render(book: Book, fmt: str) -> bytes:
    if fmt == "epub":
        return epub_bytes(book)
    if fmt == "docx":
        return docx_bytes(book)
    if fmt == "pdf":
        return pdf_bytes(book)
    raise ValueError(f"unknown export format {fmt!r}")


# -- EPUB ---------------------------------------------------------------------------------------


def _epub_date(value: str) -> str:
    """``dcterms:modified`` wants CCYY-MM-DDThh:mm:ssZ."""
    match = re.match(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})", str(value or ""))
    return f"{match.group(1)}T{match.group(2)}Z" if match else "2000-01-01T00:00:00Z"


def _xhtml(title: str, body: str) -> str:
    return ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="en">\n'
            f'<head><meta charset="utf-8"/><title>{escape(title)}</title></head>\n<body>\n{body}\n</body>\n</html>\n')


def _chapter_xhtml(chapter: BookChapter) -> str:
    parts = [f"<h2>{escape(chapter.title)}</h2>"]
    for index, scene in enumerate(chapter.scenes):
        if index:
            parts.append(f'<p class="scene-break">{SCENE_BREAK}</p>')
        parts.extend(f"<p>{escape(paragraph)}</p>" for paragraph in scene)
    return _xhtml(chapter.title, "\n".join(parts))


def epub_bytes(book: Book) -> bytes:
    """An EPUB 3 book: a title page, one XHTML file per chapter and the navigation document."""
    files = [("title.xhtml", _xhtml(book.title, f"<h1>{escape(book.title)}</h1>"))]
    files += [(f"chapter-{number}.xhtml", _chapter_xhtml(chapter)) for number, chapter in enumerate(book.chapters, 1)]
    # The title page leads the contents, so a story with no text still has the entry EPUB 3 requires.
    nav_items = "\n".join([f'<li><a href="title.xhtml">{escape(book.title)}</a></li>'] + [
        f'<li><a href="chapter-{number}.xhtml">{escape(chapter.title)}</a></li>'
        for number, chapter in enumerate(book.chapters, 1)])
    nav = _xhtml("Contents", f'<nav epub:type="toc" id="toc"><h1>Contents</h1><ol>\n{nav_items}\n</ol></nav>')
    manifest = "\n".join(
        f'<item id="f{index}" href="{name}" media-type="application/xhtml+xml"/>' for index, (name, _) in enumerate(files)
    )
    spine = "\n".join(f'<itemref idref="f{index}"/>' for index in range(len(files)))
    opf = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book-id">\n'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        f'<dc:identifier id="book-id">urn:omnix:story:{escape(book.identifier)}</dc:identifier>\n'
        f"<dc:title>{escape(book.title)}</dc:title>\n<dc:language>en</dc:language>\n"
        f'<meta property="dcterms:modified">{book.modified}</meta>\n</metadata>\n'
        f'<manifest>\n<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>\n'
        f"{manifest}\n</manifest>\n<spine>\n{spine}\n</spine>\n</package>\n"
    )
    container = ('<?xml version="1.0" encoding="utf-8"?>\n'
                 '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
                 '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                 "</rootfiles>\n</container>\n")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        # The mimetype comes first and uncompressed, so a reader can recognise the file.
        archive.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", container, compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("OEBPS/content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("OEBPS/nav.xhtml", nav, compress_type=zipfile.ZIP_DEFLATED)
        for name, text in files:
            archive.writestr(f"OEBPS/{name}", text, compress_type=zipfile.ZIP_DEFLATED)
    return buffer.getvalue()


# -- DOCX ---------------------------------------------------------------------------------------


def docx_bytes(book: Book) -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK

    document = Document()
    document.core_properties.title = book.title
    document.add_heading(book.title, level=0)
    for chapter in book.chapters:
        document.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        document.add_heading(chapter.title, level=1)
        for index, scene in enumerate(chapter.scenes):
            if index:
                document.add_paragraph(SCENE_BREAK).alignment = WD_ALIGN_PARAGRAPH.CENTER
            for paragraph in scene:
                document.add_paragraph(paragraph)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


# -- PDF ----------------------------------------------------------------------------------------

_PAGE_WIDTH, _PAGE_HEIGHT, _MARGIN = 595.0, 842.0, 72.0  # A4 in points
_TEXT_WIDTH = _PAGE_WIDTH - 2 * _MARGIN

# Helvetica's advance widths (per 1000 units) for the printable ASCII range, from its AFM metrics.
_HELVETICA = [
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
    1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
    333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
    556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
]
_WIDE = {"—": 1000, "…": 1000, "–": 556, "‘": 222, "’": 222, "“": 333, "”": 333}
# Bold glyphs are a little wider; headings are wrapped as if every glyph were this much wider.
_BOLD_SCALE = 1.08


def _width(text: str, size: float, bold: bool = False) -> float:
    units = sum(_HELVETICA[ord(char) - 32] if 32 <= ord(char) <= 126 else _WIDE.get(char, 556) for char in text)
    return units * size / 1000 * (_BOLD_SCALE if bold else 1.0)


def _wrap(text: str, size: float, bold: bool = False) -> list[str]:
    lines: list[str] = []
    line = ""
    for word in text.split():
        candidate = f"{line} {word}" if line else word
        if line and _width(candidate, size, bold) > _TEXT_WIDTH:
            lines.append(line)
            line = word
        else:
            line = candidate
        while _width(line, size, bold) > _TEXT_WIDTH and len(line) > 1:
            # A word wider than the line is broken where it runs out of room.
            cut = len(line)
            while cut > 1 and _width(line[:cut], size, bold) > _TEXT_WIDTH:
                cut -= 1
            lines.append(line[:cut])
            line = line[cut:]
    if line:
        lines.append(line)
    return lines


def _pdf_string(text: str) -> bytes:
    """A PDF literal string in WinAnsi (cp1252); a character it lacks becomes "?"."""
    raw = text.encode("cp1252", errors="replace")
    return b"(" + raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


class _PdfLayout:
    """Lays lines of text down A4 pages, starting a new page when one is full."""

    def __init__(self) -> None:
        self.pages: list[list[bytes]] = []
        self.y = 0.0
        self.new_page()

    def new_page(self) -> None:
        self.pages.append([])
        self.y = _PAGE_HEIGHT - _MARGIN

    def gap(self, points: float) -> None:
        self.y -= points

    def line(self, text: str, size: float, *, bold: bool = False, center: bool = False) -> None:
        leading = size * 1.4
        if self.y - leading < _MARGIN:
            self.new_page()
        self.y -= leading
        x = _MARGIN + (_TEXT_WIDTH - _width(text, size, bold)) / 2 if center else _MARGIN
        font = b"/F2" if bold else b"/F1"
        self.pages[-1].append(b"BT " + font + b" %.1f Tf %.2f %.2f Td " % (size, x, self.y) + _pdf_string(text) + b" Tj ET")

    def paragraph(self, text: str, size: float, *, bold: bool = False, after: float = 6.0) -> None:
        for wrapped in _wrap(text, size, bold):
            self.line(wrapped, size, bold=bold)
        self.gap(after)


def pdf_bytes(book: Book) -> bytes:
    """A plain A4 PDF in Helvetica: a title page, then each chapter from a new page."""
    layout = _PdfLayout()
    layout.gap(180)
    for line in _wrap(book.title, 24, True):
        layout.line(line, 24, bold=True, center=True)
    for chapter in book.chapters:
        layout.new_page()
        layout.paragraph(chapter.title, 16, bold=True, after=14)
        for index, scene in enumerate(chapter.scenes):
            if index:
                layout.line(SCENE_BREAK, 11, center=True)
                layout.gap(8)
            for paragraph in scene:
                layout.paragraph(paragraph, 11)
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",  # the page tree, filled in once the pages are numbered
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
        b"<< /Title " + _pdf_string(book.title) + b" /Producer (Omnix Storyteller) >>",
    ]
    page_ids: list[int] = []
    for commands in layout.pages:
        stream = b"\n".join(commands)
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        objects.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Contents %d 0 R "
                       b"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> >>"
                       % (int(_PAGE_WIDTH), int(_PAGE_HEIGHT), len(objects)))
        page_ids.append(len(objects))
    kids = b" ".join(b"%d 0 R" % number for number in page_ids)
    objects[1] = b"<< /Type /Pages /Kids [" + kids + b"] /Count %d >>" % len(page_ids)
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % number + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(b"trailer\n<< /Size %d /Root 1 0 R /Info 5 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref))
    return out.getvalue()
