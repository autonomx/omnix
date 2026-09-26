from contextlib import contextmanager
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.assets.models import AssetRecord
from app.persistence import asset_compat
from app.persistence.blob_store import LocalBlobStore


@pytest.mark.parametrize("persist_fails", [False, True])
def test_new_asset_streams_source_and_preserves_failure_cleanup(
    tmp_path, monkeypatch, persist_fails
):
    source = tmp_path / "audio.bin"
    content = b"bounded media copy" * 100_000
    source.write_bytes(content)
    asset = AssetRecord(
        id="audio-1",
        module="voice",
        type="audio",
        mime_type="audio/wav",
        storage_path=str(source),
        created_at="2026-09-26T00:00:00Z",
    )
    store = asset_compat.PostgresSharedAssetStoreAdapter.__new__(
        asset_compat.PostgresSharedAssetStoreAdapter
    )
    store.database = object()
    store.context = object()
    store.blob_store = LocalBlobStore(tmp_path / "blobs")
    rows = []

    def create(context, row):
        rows.append(row)
        if persist_fails:
            raise RuntimeError("persistence failed")
        return row

    @contextmanager
    def work(database):
        yield SimpleNamespace(
            assets=SimpleNamespace(get_asset=lambda *args: None, create=create),
            rollback=lambda: None,
            commit=lambda: None,
        )

    def no_buffered_read(self):
        raise AssertionError("asset ingestion must not load the whole file")

    monkeypatch.setattr(asset_compat, "unit_of_work", work)
    monkeypatch.setattr(Path, "read_bytes", no_buffered_read)
    monkeypatch.setattr(store, "_asset", lambda record: asset)
    if persist_fails:
        with pytest.raises(RuntimeError, match="persistence failed"):
            store.upsert_asset(asset)
        assert not store.blob_store.exists("assets/audio-1/audio.bin")
    else:
        assert store.upsert_asset(asset) is asset
        assert store.blob_store.exists("assets/audio-1/audio.bin")
    assert rows[0]["byte_size"] == len(content)
    assert rows[0]["checksum_sha256"] == hashlib.sha256(content).hexdigest()
