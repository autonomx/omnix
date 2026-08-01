from __future__ import annotations

import json
import threading
from pathlib import Path

from app.assets.models import AssetRecord, AssetType
from app.assets.store import SharedAssetStore


class _ObservedStore(SharedAssetStore):
    def __init__(
        self,
        manifest_path: Path,
        *,
        first_loaded: threading.Event,
        release_first: threading.Event,
        second_loaded: threading.Event,
    ) -> None:
        super().__init__(manifest_path)
        self.first_loaded = first_loaded
        self.release_first = release_first
        self.second_loaded = second_loaded

    def _load_manifest(self) -> dict[str, AssetRecord]:
        manifest = super()._load_manifest()
        if threading.current_thread().name == "asset-writer-first":
            self.first_loaded.set()
            if not self.release_first.wait(timeout=2):
                raise TimeoutError("first writer was not released")
        elif threading.current_thread().name == "asset-writer-second":
            self.second_loaded.set()
        return manifest


def _asset(asset_id: str, storage_path: Path) -> AssetRecord:
    return AssetRecord(
        id=asset_id,
        module="image-generation",
        type=AssetType.IMAGE,
        mime_type="image/png",
        storage_path=str(storage_path),
        created_at="2026-07-31T00:00:00+00:00",
    )


def test_concurrent_manifest_upserts_do_not_drop_assets(tmp_path: Path) -> None:
    manifest_path = tmp_path / "assets" / "manifest.json"
    first_loaded = threading.Event()
    release_first = threading.Event()
    second_loaded = threading.Event()
    errors: list[BaseException] = []

    first_store = _ObservedStore(
        manifest_path,
        first_loaded=first_loaded,
        release_first=release_first,
        second_loaded=second_loaded,
    )
    second_store = _ObservedStore(
        manifest_path,
        first_loaded=first_loaded,
        release_first=release_first,
        second_loaded=second_loaded,
    )

    def write(store: SharedAssetStore, asset: AssetRecord) -> None:
        try:
            store.upsert_asset(asset)
        except BaseException as exc:  # pragma: no cover - surfaced by the assertion below
            errors.append(exc)

    first = threading.Thread(
        target=write,
        args=(first_store, _asset("image:first", tmp_path / "first.png")),
        name="asset-writer-first",
    )
    second = threading.Thread(
        target=write,
        args=(second_store, _asset("image:second", tmp_path / "second.png")),
        name="asset-writer-second",
    )

    first.start()
    assert first_loaded.wait(timeout=2)
    second.start()

    assert not second_loaded.wait(timeout=0.1)
    release_first.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == []
    assert second_loaded.is_set()

    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert set(raw["assets"]) == {"image:first", "image:second"}
    assert list(manifest_path.parent.glob("*.tmp")) == []
