"""Saving a story works with the PostgreSQL asset store (no manifest on disk)."""
from __future__ import annotations

from pathlib import Path

from app.assets.models import AssetRecord
from app.story.asset_save import SaveStoryAssetRequest, save_story_asset


class _BlobBackedStore:
    """Like PostgresSharedAssetStoreAdapter: copies the file on upsert."""

    def __init__(self) -> None:
        self.copied: dict[str, str] = {}
        self.staged: list[Path] = []

    def upsert_asset(self, asset: AssetRecord) -> AssetRecord:
        staged = Path(asset.storage_path)
        self.staged.append(staged)
        self.copied[asset.id] = staged.read_text(encoding="utf-8")
        return asset.model_copy(update={"storage_path": "", "storage_key": f"assets/{asset.id}"})


def test_story_is_staged_temporarily_and_stored_through_the_asset_store() -> None:
    store = _BlobBackedStore()
    saved = save_story_asset(store, SaveStoryAssetRequest(title="Night Train", content="Chapter one."))  # type: ignore[arg-type]
    assert saved.asset.storage_key == f"assets/{saved.asset.id}"
    assert store.copied[saved.asset.id].strip() == "Chapter one."
    assert saved.content == "Chapter one."
    # The staging file is removed once the store has taken the content.
    assert store.staged and not store.staged[0].exists()
