from __future__ import annotations

from app.assets import AssetType, SharedAssetStore
from app.assets import canonical_voice_clones


def test_canonical_voice_clones_are_kept_when_environment_override_is_empty(
    tmp_path,
    monkeypatch,
) -> None:
    resources_dir = tmp_path / "resources"
    canonical_dir = resources_dir / "voice_clones"
    canonical_dir.mkdir(parents=True)
    maya_path = canonical_dir / "Maya.wav"
    maya_path.write_bytes(b"voice-audio")

    empty_override = tmp_path / "empty-override"
    empty_override.mkdir()
    monkeypatch.setenv("OMNIX_VOICE_CLONES_DIR", str(empty_override))
    monkeypatch.delenv("OMNIX_VOICE_CLONES_FILE", raising=False)
    monkeypatch.setattr(canonical_voice_clones, "resources_root", lambda: resources_dir)

    store = SharedAssetStore(tmp_path / "assets" / "manifest.json")
    voice_assets = [
        asset
        for asset in store.list_assets().assets
        if asset.type == AssetType.VOICE_PROFILE
    ]

    assert [asset.id for asset in voice_assets] == ["voice-cloning:Maya"]
    assert voice_assets[0].storage_path == str(maya_path)
    assert voice_assets[0].metadata["profile_name"] == "Maya"
    assert voice_assets[0].metadata["recovered_from_canonical_file"] is True
