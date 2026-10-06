"""Asset content helpers over file-backed, local-blob and S3-blob assets (WP-5.8)."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import uuid

import httpx
import pytest

from app.assets import content
from app.assets.models import AssetRecord, AssetType
from app.persistence.blob_store import LocalBlobStore
from app.persistence.s3_blob_store import S3BlobStore, S3Settings

PAYLOAD = b"RIFF" + bytes(range(256)) * 8


def _asset(**fields) -> AssetRecord:
    return AssetRecord(
        id=fields.pop("id", "asset:test"),
        module="test",
        type=AssetType.AUDIO,
        mime_type="audio/wav",
        created_at="2026-10-01T00:00:00+00:00",
        **fields,
    )


def _s3_store() -> S3BlobStore:
    endpoint = os.environ.get("OMNIX_TEST_S3_ENDPOINT")
    if not endpoint:
        pytest.skip("OMNIX_TEST_S3_ENDPOINT is required for remote asset content")
    settings = S3Settings(
        endpoint=endpoint,
        bucket=f"omnix-content-{uuid.uuid4().hex[:12]}",
        access_key_id=os.environ.get("OMNIX_TEST_S3_ACCESS_KEY_ID", ""),
        secret_access_key=os.environ.get("OMNIX_TEST_S3_SECRET_ACCESS_KEY", ""),
    )
    store = S3BlobStore(settings)
    path = f"/{settings.bucket}"
    headers = store.signer.sign_headers("PUT", path, payload_sha256=hashlib.sha256(b"").hexdigest())
    assert httpx.put(f"{endpoint.rstrip('/')}{path}", headers=headers, timeout=30).status_code in {200, 409}
    return store


@pytest.fixture(params=["file", "local-blob", "s3-blob"])
def stored_asset(request, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(content, "resources_data_root", lambda: tmp_path / "data")
    if request.param == "file":
        path = tmp_path / "clone.wav"
        path.write_bytes(PAYLOAD)
        yield _asset(storage_path=str(path)), None
        return
    store = LocalBlobStore(tmp_path / "blobs") if request.param == "local-blob" else _s3_store()
    record = store.put_bytes("assets/clone/clone.wav", PAYLOAD)
    monkeypatch.setattr(content, "default_blob_store", lambda: store)
    yield _asset(storage_key=record["storage_key"], checksum_sha256=record["checksum_sha256"]), store


def test_reads_checksums_and_paths_work_for_every_backend(stored_asset) -> None:
    asset, _store = stored_asset
    assert content.asset_available(asset) is True
    assert content.read_asset_bytes(asset) == PAYLOAD
    with content.open_asset(asset) as handle:
        assert handle.read() == PAYLOAD
    assert content.asset_checksum(asset) == hashlib.sha256(PAYLOAD).hexdigest()
    path = content.materialize_asset(asset)
    assert path.read_bytes() == PAYLOAD
    assert path.suffix == ".wav"
    # Materialization is stable: the same file on a second call.
    assert content.materialize_asset(asset) == path
    with pytest.raises(ValueError):
        content.read_asset_bytes(asset, max_bytes=10)


def test_deleted_content_is_reported_unavailable(stored_asset) -> None:
    asset, _store = stored_asset
    assert content.delete_asset_content(asset) is True
    assert content.asset_available(asset) is False
    assert content.delete_asset_content(asset) is False
    with pytest.raises(content.AssetContentUnavailable):
        content.open_asset(asset)


def test_remote_materialization_rejects_tampered_content(tmp_path: Path, monkeypatch) -> None:
    store = _s3_store()
    record = store.put_bytes("assets/tamper/a.wav", PAYLOAD)
    monkeypatch.setattr(content, "default_blob_store", lambda: store)
    monkeypatch.setattr(content, "resources_data_root", lambda: tmp_path / "data")
    asset = _asset(storage_key=record["storage_key"], checksum_sha256="0" * 64)
    with pytest.raises(Exception) as caught:
        content.materialize_asset(asset)
    assert "checksum" in str(caught.value)
    assert not list((tmp_path / "data").rglob("*.wav"))


def test_empty_local_files_are_not_available(tmp_path: Path) -> None:
    empty = tmp_path / "empty.png"
    empty.write_bytes(b"")
    assert content.asset_available(_asset(storage_path=str(empty))) is False
    assert content.asset_available(_asset(storage_path=str(tmp_path / "missing.png"))) is False
    assert content.local_asset_path(_asset(storage_path=str(tmp_path / "missing.png"))) == tmp_path / "missing.png"
