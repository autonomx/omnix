from __future__ import annotations

import json

from app.assets import AssetRecord, AssetType, SharedAssetStore


def test_shared_asset_store_reads_legacy_voice_clone_profiles(tmp_path, monkeypatch) -> None:
    import app.shared as shared

    voice_dir = tmp_path / "voice_clones"
    voice_dir.mkdir()
    (voice_dir / "narrator.wav").write_bytes(b"RIFF")
    voice_manifest = voice_dir / "voice_clones.json"
    voice_manifest.write_text(
        json.dumps(
            {
                "Narrator": {
                    "speaker": "default",
                    "language": "en",
                    "voice_clone_id": "narrator",
                    "has_audio": True,
                    "is_preloaded": True,
                    "gender": "neutral",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(shared, "VOICE_CLONES_DIR", str(voice_dir))
    monkeypatch.setattr(shared, "VOICE_CLONES_FILE", str(voice_manifest))

    store = SharedAssetStore(tmp_path / "assets" / "manifest.json")

    assets = store.list_assets().assets

    voice_assets = [asset for asset in assets if asset.type == AssetType.VOICE_PROFILE]
    assert len(voice_assets) == 1
    assert voice_assets[0].id == "voice-cloning:Narrator"
    assert voice_assets[0].module == "voice-cloning"
    assert voice_assets[0].mime_type == "audio/wav"
    assert voice_assets[0].storage_path.endswith("narrator.wav")
    assert voice_assets[0].metadata["voice_clone_id"] == "narrator"
    assert voice_assets[0].metadata["has_audio"] is True
    assert voice_assets[0].compat["legacy_voice_id"] == "Narrator"

    assert not store.manifest_path.exists()


def test_manifest_asset_overrides_matching_legacy_voice_clone(tmp_path, monkeypatch) -> None:
    import app.shared as shared

    voice_dir = tmp_path / "voice_clones"
    voice_dir.mkdir()
    voice_manifest = voice_dir / "voice_clones.json"
    voice_manifest.write_text(
        json.dumps({"Narrator": {"voice_clone_id": "legacy-narrator"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(shared, "VOICE_CLONES_DIR", str(voice_dir))
    monkeypatch.setattr(shared, "VOICE_CLONES_FILE", str(voice_manifest))

    store = SharedAssetStore(tmp_path / "assets" / "manifest.json")
    store.upsert_asset(
        AssetRecord(
            id="voice-cloning:Narrator",
            module="voice-cloning",
            type=AssetType.VOICE_PROFILE,
            mime_type="application/octet-stream",
            storage_path="shared/profile.bin",
            metadata={"source": "shared-manifest"},
            created_at="2026-01-01T00:00:00+00:00",
        )
    )

    assets = {asset.id: asset for asset in store.list_assets().assets}

    assert assets["voice-cloning:Narrator"].storage_path == "shared/profile.bin"
    assert assets["voice-cloning:Narrator"].metadata == {"source": "shared-manifest"}
