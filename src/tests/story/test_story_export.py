"""ST-6.5: a story exports as EPUB, DOCX and PDF, and each file opens with the story in it."""
from __future__ import annotations

import io
import zipfile
import xml.etree.ElementTree as ET

import pytest

from app.apps.story import export
from app.apps.story.contracts import StoryProject

_LONG = ("The tide went out and kept going, past the reef and the old pier, until the bay was a plain of wet sand "
         "that shone under the lamp. ") * 12


def _project() -> StoryProject:
    def page(page_id, chapter, title, blocks, hidden=False):
        return {"id": page_id, "chapter": chapter, "position": 0, "title": title, "blocks": blocks, "hidden": hidden,
                "created_at": "2026-11-26T10:00:00+00:00"}

    return StoryProject.model_validate({
        "id": "project_fixture", "title": "Salt & Letters", "premise": "", "mode": "writing", "tone": "", "writing_style": "",
        "origin_kind": "new", "origin_ref": "", "created_at": "2026-11-26T10:00:00+00:00",
        "updated_at": "2026-11-26T11:30:05.123+00:00",
        "pages": [
            page("p1", 1, "", [{"text": "Wren sorts the mail at the door."},
                               {"kind": "dialogue", "text": "“Who writes to us?” she asks.", "speaker_id": "wren"}]),
            page("p2", 1, "", [{"text": _LONG}]),
            page("p-hidden", 1, "", [{"text": "A branch nobody kept."}], hidden=True),
            page("p3", 2, "Chapter 2: Salt Ink", [{"text": "A second sheet — softer — waits inside (folded)."}]),
        ],
    })


def test_the_book_is_the_visible_pages_in_chapters_of_scenes():
    book = export.book_of(_project())
    assert [chapter.title for chapter in book.chapters] == ["Chapter 1", "Chapter 2: Salt Ink"]
    assert [len(chapter.scenes) for chapter in book.chapters] == [2, 1]
    assert book.chapters[0].scenes[0] == ["Wren sorts the mail at the door.", "“Who writes to us?” she asks."]
    assert "A branch nobody kept." not in str(book)
    assert book.modified == "2026-11-26T11:30:05Z"
    assert export.file_name(book, "epub") == "salt-letters.epub"


def test_the_epub_opens_with_its_chapters_and_navigation():
    data = export.render(export.book_of(_project()), "epub")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        first = archive.infolist()[0]
        assert (first.filename, first.compress_type) == ("mimetype", zipfile.ZIP_STORED)
        assert archive.read("mimetype") == b"application/epub+zip"
        container = ET.fromstring(archive.read("META-INF/container.xml"))
        opf_path = container.find(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile").get("full-path")
        opf = ET.fromstring(archive.read(opf_path))
        ns = {"opf": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/"}
        assert opf.find(".//dc:title", ns).text == "Salt & Letters"
        hrefs = {item.get("id"): item.get("href") for item in opf.findall(".//opf:item", ns)}
        spine = [hrefs[ref.get("idref")] for ref in opf.findall(".//opf:itemref", ns)]
        assert spine == ["title.xhtml", "chapter-1.xhtml", "chapter-2.xhtml"]
        # Every content file is well-formed XHTML.
        texts = {name: ET.fromstring(archive.read(f"OEBPS/{name}")) for name in [*spine, "nav.xhtml"]}
    chapter_one = "".join(texts["chapter-1.xhtml"].itertext())
    assert "“Who writes to us?” she asks." in chapter_one and export.SCENE_BREAK in chapter_one
    assert "Chapter 2: Salt Ink" in "".join(texts["nav.xhtml"].itertext())


def test_the_docx_opens_with_its_headings_and_paragraphs():
    from docx import Document

    document = Document(io.BytesIO(export.render(export.book_of(_project()), "docx")))
    assert document.core_properties.title == "Salt & Letters"
    headings = [(p.style.name, p.text) for p in document.paragraphs if p.style.name.startswith(("Title", "Heading"))]
    assert headings == [("Title", "Salt & Letters"), ("Heading 1", "Chapter 1"), ("Heading 1", "Chapter 2: Salt Ink")]
    texts = [paragraph.text for paragraph in document.paragraphs]
    assert "“Who writes to us?” she asks." in texts and _LONG.strip() in texts


def test_control_characters_pasted_into_a_story_stay_out_of_its_book():
    from docx import Document

    project = _project().model_copy(update={"title": "Salt\x0c Letters"})
    project.pages[0].title = "Ink\x0b"
    project.pages[0].blocks[0].text = "Wren\x0b sorts the mail."  # saved before such text was refused
    book = export.book_of(project)
    assert book.title == "Salt Letters" and book.chapters[0].title == "Ink"
    assert book.chapters[0].scenes[0][0] == "Wren sorts the mail."
    document = Document(io.BytesIO(export.render(book, "docx")))
    assert document.paragraphs[0].text == "Salt Letters"
    with zipfile.ZipFile(io.BytesIO(export.render(book, "epub"))) as archive:
        ET.fromstring(archive.read("OEBPS/chapter-1.xhtml"))
    # A block's text is cleaned as it is read, so an edit cannot save the character either.
    assert StoryProject.model_validate(_project().model_dump() | {"pages": [
        {**_project().model_dump()["pages"][0], "blocks": [{"text": "a\x0cb\tc"}]}]}).pages[0].blocks[0].text == "ab\tc"


def test_the_pdf_opens_with_the_story_on_its_pages():
    pypdf = pytest.importorskip("pypdf")
    reader = pypdf.PdfReader(io.BytesIO(export.render(export.book_of(_project()), "pdf")))
    assert reader.metadata.title == "Salt & Letters"
    pages = [page.extract_text() for page in reader.pages]
    # A title page, then each chapter from a new page.
    assert len(pages) == 3
    assert "Salt & Letters" in pages[0]
    assert "Wren sorts the mail at the door." in pages[1]
    assert "Chapter 2: Salt Ink" in pages[-1] and "softer" in pages[-1]
    text = " ".join(pages)
    assert "“Who writes to us?”" in text and "(folded)" in text
    # Lines are wrapped inside the margins: no extracted line is longer than the page can hold.
    assert max(len(line) for page in pages for line in page.splitlines()) < 110


def test_a_long_chapter_runs_on_over_pdf_pages_without_losing_a_line():
    pypdf = pytest.importorskip("pypdf")
    paragraphs = [f"Paragraph {number}. {_LONG}" for number in range(1, 13)]
    book = export.Book(identifier="b", title="Long", modified="2026-11-26T00:00:00Z",
                       chapters=[export.BookChapter(title="Chapter 1", scenes=[paragraphs])])
    reader = pypdf.PdfReader(io.BytesIO(export.pdf_bytes(book)))
    assert len(reader.pages) > 3
    text = " ".join(page.extract_text() for page in reader.pages)
    assert all(f"Paragraph {number}." in text for number in range(1, 13))


def test_a_chapter_titled_as_the_book_is_headed_by_its_number_and_the_nav_is_never_empty():
    project = _project()
    project.pages[0].title = "salt & letters"  # a drafted opening page carries the story's title
    book = export.book_of(project)
    assert [chapter.title for chapter in book.chapters] == ["Chapter 1", "Chapter 2: Salt Ink"]
    with zipfile.ZipFile(io.BytesIO(export.render(book, "epub"))) as archive:
        nav = ET.fromstring(archive.read("OEBPS/nav.xhtml"))
    links = [link.get("href") for link in nav.iter("{http://www.w3.org/1999/xhtml}a")]
    assert links[0] == "title.xhtml" and "chapter-1.xhtml" in links
    empty = export.Book(identifier="b", title="Blank", modified="2026-11-26T00:00:00Z", chapters=[])
    with zipfile.ZipFile(io.BytesIO(export.render(empty, "epub"))) as archive:
        nav = ET.fromstring(archive.read("OEBPS/nav.xhtml"))
    assert [link.get("href") for link in nav.iter("{http://www.w3.org/1999/xhtml}a")] == ["title.xhtml"]
