from __future__ import annotations

import json

from app.assets import AssetType, SharedAssetStore
import pytest


@pytest.fixture(autouse=True)
def _isolated_resources_root(tmp_path, monkeypatch):
    # Discovery always scans resources_root()/voice_clones; never the operator's.
    root = tmp_path / "resources"
    for owner in ("app.assets.canonical_voice_clones", "app.assets.voice_clone_assets"):
        monkeypatch.setattr(f"{owner}.resources_root", lambda: root)
    return root


def _voice_assets(store: SharedAssetStore):
    return [asset for asset in store.list_assets().assets if asset.type == AssetType.VOICE_PROFILE]


