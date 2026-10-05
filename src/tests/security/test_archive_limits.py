"""Uploaded archives are refused before they expand past their limits (ASVS 12.1.2)."""
from __future__ import annotations

import io
import zipfile

import pytest

from app.audiobook import extraction
from app.characters import live2d_avatar


def _archive(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


@pytest.mark.parametrize("reader", [extraction._epub_chapters, extraction._docx_chapters])
def test_documents_that_expand_too_far_are_refused(reader, monkeypatch) -> None:
    monkeypatch.setattr(extraction, "MAX_EPUB_UNCOMPRESSED_BYTES", 1_000)
    bomb = _archive({"word/document.xml": b"\0" * 5_000})
    with pytest.raises(extraction.UnsupportedSource, match="uncompressed content exceeds"):
        reader(bomb)


@pytest.mark.parametrize("reader", [extraction._epub_chapters, extraction._docx_chapters])
def test_documents_with_too_many_files_are_refused(reader, monkeypatch) -> None:
    monkeypatch.setattr(extraction, "MAX_ARCHIVE_MEMBERS", 5)
    crowded = _archive({f"part-{index}.xml": b"x" for index in range(6)})
    with pytest.raises(extraction.UnsupportedSource, match="more than 5 files"):
        reader(crowded)


def test_a_live2d_archive_that_expands_too_far_is_refused(monkeypatch) -> None:
    monkeypatch.setattr(live2d_avatar, "MAX_LIVE2D_ARCHIVE_BYTES", 1_000)
    with zipfile.ZipFile(io.BytesIO(_archive({"a.moc3": b"\0" * 600, "b.png": b"\0" * 600}))) as archive:
        with pytest.raises(ValueError, match="expands beyond"):
            live2d_avatar._safe_zip_members(archive)


def test_a_live2d_archive_with_too_many_entries_is_refused(monkeypatch) -> None:
    monkeypatch.setattr(live2d_avatar, "MAX_LIVE2D_ARCHIVE_MEMBERS", 3)
    with zipfile.ZipFile(io.BytesIO(_archive({f"m{index}.json": b"{}" for index in range(4)}))) as archive:
        with pytest.raises(ValueError, match="more than 3 entries"):
            live2d_avatar._safe_zip_members(archive)


def test_a_normal_live2d_archive_passes() -> None:
    with zipfile.ZipFile(io.BytesIO(_archive({"model/a.model3.json": b"{}", "model/a.moc3": b"moc"}))) as archive:
        assert set(live2d_avatar._safe_zip_members(archive)) == {"model/a.model3.json", "model/a.moc3"}
