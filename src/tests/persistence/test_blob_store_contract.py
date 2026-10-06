"""BlobStore contract: the same behaviour from LocalBlobStore and S3BlobStore.

The S3 variant runs when ``OMNIX_TEST_S3_ENDPOINT`` points at a disposable
S3-compatible server (CI uses SeaweedFS), with ``OMNIX_TEST_S3_ACCESS_KEY_ID``
and ``OMNIX_TEST_S3_SECRET_ACCESS_KEY``.
"""
from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import uuid

import httpx
import pytest

from app.persistence.blob_store import BlobIntegrityError, InvalidBlobKey, LocalBlobStore
from app.persistence.s3_blob_store import S3BlobStore, S3Settings


def _s3_store() -> S3BlobStore:
    endpoint = os.environ.get("OMNIX_TEST_S3_ENDPOINT")
    if not endpoint:
        pytest.skip("OMNIX_TEST_S3_ENDPOINT is required for the S3 BlobStore contract")
    settings = S3Settings(
        endpoint=endpoint,
        bucket=f"omnix-contract-{uuid.uuid4().hex[:12]}",
        access_key_id=os.environ.get("OMNIX_TEST_S3_ACCESS_KEY_ID", ""),
        secret_access_key=os.environ.get("OMNIX_TEST_S3_SECRET_ACCESS_KEY", ""),
        prefix="contract",
    )
    store = S3BlobStore(settings)
    path = f"/{settings.bucket}"
    headers = store.signer.sign_headers("PUT", path, payload_sha256=hashlib.sha256(b"").hexdigest())
    response = httpx.put(f"{endpoint.rstrip('/')}{path}", headers=headers, timeout=30)
    assert response.status_code in {200, 409}, response.text
    return store


@pytest.fixture(params=["local", "s3"])
def store(request, tmp_path: Path):
    if request.param == "local":
        yield LocalBlobStore(tmp_path / "blobs")
        return
    s3 = _s3_store()
    try:
        yield s3
    finally:
        s3.close()


def test_put_and_read_bytes_round_trip_with_checksums(store) -> None:
    content = b"omnix blob contract"
    first = store.put_bytes("assets/a/one.bin", content)
    assert first["created"] is True
    assert first["byte_size"] == len(content)
    assert first["checksum_sha256"] == hashlib.sha256(content).hexdigest()
    assert first["storage_key"] == "assets/a/one.bin"
    assert store.put_bytes("assets/a/one.bin", content)["created"] is False
    assert store.read_bytes("assets/a/one.bin", expected_checksum=first["checksum_sha256"]) == content
    with pytest.raises(BlobIntegrityError):
        store.read_bytes("assets/a/one.bin", expected_checksum="0" * 64)


def test_streams_are_size_capped_and_leave_nothing_behind(store) -> None:
    payload = os.urandom(3 * 1024 * 1024 + 17)
    record = store.put_stream("big/stream.bin", io.BytesIO(payload), content_type="application/octet-stream")
    assert record["byte_size"] == len(payload)
    with store.open("big/stream.bin") as handle:
        assert handle.read() == payload
    with pytest.raises(ValueError):
        store.put_stream("big/too-large.bin", io.BytesIO(payload), max_bytes=1024)
    assert store.exists("big/too-large.bin") is False


def test_verified_open_copy_and_stage(store, tmp_path: Path) -> None:
    content = b"verified content"
    checksum = store.put_bytes("v/file.txt", content)["checksum_sha256"]
    with store.open_verified("v/file.txt", expected_checksum=checksum) as handle:
        assert handle.read() == content
    with pytest.raises(BlobIntegrityError):
        store.open_verified("v/file.txt", expected_checksum="f" * 64)
    store.copy_verified_to("v/file.txt", tmp_path / "copy.txt", expected_checksum=checksum)
    assert (tmp_path / "copy.txt").read_bytes() == content
    store.stage_verified_to("v/file.txt", tmp_path / "stage.txt", expected_checksum=checksum)
    assert (tmp_path / "stage.txt").read_bytes() == content


def test_put_file_exists_and_delete(store, tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    source.write_bytes(b"RIFF" + bytes(64))
    record = store.put_file("audio/source.wav", source)
    assert record["byte_size"] == 68
    assert store.exists("audio/source.wav") is True
    assert store.delete("audio/source.wav") is True
    assert store.exists("audio/source.wav") is False
    assert store.delete("audio/source.wav") is False
    with pytest.raises(FileNotFoundError):
        store.read_bytes("audio/source.wav")


@pytest.mark.parametrize("key", ["../escape", "/abs", "a//b"])
def test_unsafe_keys_are_rejected(store, key: str) -> None:
    with pytest.raises(InvalidBlobKey):
        store.put_bytes(key, b"x")


def test_presigned_download(store) -> None:
    store.put_bytes("share/report.txt", b"shared")
    url = store.presign_get("share/report.txt", 60)
    if isinstance(store, LocalBlobStore):
        assert url is None  # served through the gateway instead
        return
    response = httpx.get(url, timeout=30)
    assert response.status_code == 200
    assert response.content == b"shared"
