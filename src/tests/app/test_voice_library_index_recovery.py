from __future__ import annotations

import json

from app.assets import AssetType, SharedAssetStore


def _configure_voice_paths(tmp_path, monkeypatch):
    from app import shared

    voice_dir = tmp_path / "voice_clones"
    voice_dir.mkdir()
    voice_manifest = voice_dir / "voice_clones.json"
    monkeypatch.setattr(shared, "VOICE_CLONES_DIR", str(voice_dir))
    monkeypatch.setattr(shared, "VOICE_CLONES_FILE", str(voice_manifest))
    return voice_dir, voice_manifest


def test_voice_library_recovers_audio_files_when_manifests_are_missing_or_invalid(tmp_path, monkeypatch) -> None:
    voice_dir, voice_manifest = _configure_voice_paths(tmp_path, monkeypatch)
    voice_manifest.write_text("{not-valid-json", encoding="utf-8")
    (voice_dir / "maya.webm").write_bytes(b"voice-audio")
    (voice_dir / "maya.json").write_text(
        json.dumps({"profile_name": "Maya Recovery", "voice_id": "maya", "language": "English"}),
        encoding="utf-8",
    )
    shared_manifest = tmp_path / "assets" / "manifest.json"
    shared_manifest.parent.mkdir()
    shared_manifest.write_text(
        json.dumps({"assets": {"broken": {"id": "broken", "type": "not-an-asset"}}}),
        encoding="utf-8",
    )

    assets = SharedAssetStore(shared_manifest).list_assets().assets
    voice_assets = [asset for asset in assets if asset.type == AssetType.VOICE_PROFILE]

    assert len(voice_assets) == 1
    asset = voice_assets[0]
    assert asset.id == "voice-cloning:Maya-Recovery"
    assert asset.storage_path.endswith("maya.webm")
    assert asset.mime_type == "audio/webm"
    assert asset.metadata["profile_name"] == "Maya Recovery"
    assert asset.metadata["recovered_from_file"] is True


def test_voice_library_reads_wrapped_list_manifest_and_non_wav_clone(tmp_path, monkeypatch) -> None:
    voice_dir, voice_manifest = _configure_voice_paths(tmp_path, monkeypatch)
    clone_path = voice_dir / "narrator.ogg"
    clone_path.write_bytes(b"voice-audio")
    voice_manifest.write_text(
        json.dumps({
  "schema_version": 2,
  "voices": [{
      "profile_name": "Narrator Prime",
      "voice_id": "narrator",
      "voice_clone_id": "narrator",
      "source_path": str(clone_path),
      "language": "English",
  }],
        }),
        encoding="utf-8",
    )

    assets = SharedAssetStore(tmp_path / "assets" / "manifest.json").list_assets().assets
    voice_assets = [asset for asset in assets if asset.type == AssetType.VOICE_PROFILE]

    assert len(voice_assets) == 1
    asset = voice_assets[0]
    assert asset.id == "voice-cloning:Narrator-Prime"
    assert asset.storage_path == str(clone_path)
    assert asset.mime_type == "audio/ogg"
    assert asset.metadata["voice_id"] == "narrator"
