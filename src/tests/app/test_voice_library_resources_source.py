from __future__ import annotations

import json

from app.assets import AssetType, SharedAssetStore


def _voice_assets(store: SharedAssetStore):
    return [asset for asset in store.list_assets().assets if asset.type == AssetType.VOICE_PROFILE]


def test_voice_library_reads_audio_directly_from_resources_voice_clones(tmp_path, monkeypatch) -> None:
    voice_dir = tmp_path / "resources" / "voice_clones"
    voice_dir.mkdir(parents=True)
    clone_path = voice_dir / "Maya.wav"
    clone_path.write_bytes(b"voice-audio")

    monkeypatch.setenv("OMNIX_VOICE_CLONES_DIR", str(voice_dir))
    monkeypatch.delenv("OMNIX_VOICE_CLONES_FILE", raising=False)

    assets = _voice_assets(SharedAssetStore(tmp_path / "assets" / "manifest.json"))

    assert len(assets) == 1
    assert assets[0].id == "voice-cloning:Maya"
    assert assets[0].storage_path == str(clone_path)
    assert assets[0].metadata["profile_name"] == "Maya"
    assert assets[0].metadata["recovered_from_file"] is True


def test_voice_library_recursively_reads_clone_folders_and_metadata(tmp_path, monkeypatch) -> None:
    voice_dir = tmp_path / "resources" / "voice_clones"
    maya_dir = voice_dir / "maya"
    maya_dir.mkdir(parents=True)
    clone_path = maya_dir / "reference.webm"
    clone_path.write_bytes(b"voice-audio")
    (maya_dir / "metadata.json").write_text(
        json.dumps({"profile_name": "Maya Prime", "voice_id": "maya-prime", "language": "English"}),
        encoding="utf-8",
    )

    monkeypatch.setenv("OMNIX_VOICE_CLONES_DIR", str(voice_dir))
    monkeypatch.delenv("OMNIX_VOICE_CLONES_FILE", raising=False)

    assets = _voice_assets(SharedAssetStore(tmp_path / "assets" / "manifest.json"))

    assert len(assets) == 1
    assert assets[0].id == "voice-cloning:Maya-Prime"
    assert assets[0].storage_path == str(clone_path)
    assert assets[0].metadata["voice_id"] == "maya-prime"
    assert assets[0].metadata["relative_path"] == str(clone_path.relative_to(voice_dir))
