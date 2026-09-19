from __future__ import annotations

from pathlib import Path

import pytest

from app.persistence.blob_store import BlobIntegrityError, InvalidBlobKey, LocalBlobStore


def test_blob_store_round_trip_is_idempotent(tmp_path: Path) -> None:
    store = LocalBlobStore(tmp_path / "blobs")
    first = store.put_bytes("audio/sample.bin", b"omnix")
    second = store.put_bytes("audio/sample.bin", b"omnix")

    assert first["created"] is True
    assert second["created"] is False
    assert first["checksum_sha256"] == second["checksum_sha256"]
    assert store.read_bytes(
        "audio/sample.bin", expected_checksum=first["checksum_sha256"]
    ) == b"omnix"


def test_blob_store_rejects_path_escape(tmp_path: Path) -> None:
    store = LocalBlobStore(tmp_path / "blobs")
    for key in ("../secret", "/absolute", "a//b", "a/./b"):
        with pytest.raises(InvalidBlobKey):
            store.put_bytes(key, b"blocked")


def test_blob_store_detects_integrity_failure(tmp_path: Path) -> None:
    store = LocalBlobStore(tmp_path / "blobs")
    record = store.put_bytes("reports/result.txt", b"expected")
    Path(record["path"]).write_bytes(b"tampered")
    with pytest.raises(BlobIntegrityError):
        store.read_bytes(
            "reports/result.txt", expected_checksum=record["checksum_sha256"]
        )


def test_blob_store_delete_removes_empty_directories(tmp_path: Path) -> None:
    store = LocalBlobStore(tmp_path / "blobs")
    store.put_bytes("images/portraits/a.png", b"png")
    assert store.delete("images/portraits/a.png") is True
    assert store.exists("images/portraits/a.png") is False
    assert (tmp_path / "blobs").is_dir()


def test_large_file_copy_and_verified_stage_are_atomic(tmp_path: Path) -> None:
    store = LocalBlobStore(tmp_path / "blobs")
    source = tmp_path / "source.bin"
    source.write_bytes(b"one megabyte\n" * 100_000)
    saved = store.put_file("audio/book.bin", source)
    stage = tmp_path / "stage.bin"
    store.copy_verified_to("audio/book.bin", stage,
                           expected_checksum=saved["checksum_sha256"])
    assert stage.read_bytes() == source.read_bytes()
    Path(saved["path"]).write_bytes(b"corrupt")
    stage.write_bytes(b"keep me")
    with pytest.raises(BlobIntegrityError):
        store.copy_verified_to("audio/book.bin", stage,
                               expected_checksum=saved["checksum_sha256"])
    assert stage.read_bytes() == b"keep me"
