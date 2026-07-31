from __future__ import annotations

from pathlib import Path

from app.assets import AssetType, SharedAssetStore
from app.assets import voice_clone_assets as voice_discovery


def test_voice_library_scans_flat_resources_directory(tmp_path, monkeypatch) -> None:
    clone_dir = tmp_path / "voice_clones"
    clone_dir.mkdir()
    for name in ("Anaka.wav", "Donald Trump.wav", "Maya.wav", "Vic Cyberpunk.wav"):
        (clone_dir / name).write_bytes(b"voice-audio")

    monkeypatch.setenv("OMNIX_VOICE_CLONES_DIR", str(clone_dir))
    assets = SharedAssetStore(tmp_path / "assets" / "manifest.json").list_assets().assets
    voices = [asset for asset in assets if asset.type == AssetType.VOICE_PROFILE]

    assert {asset.metadata["profile_name"] for asset in voices} == {
        "Anaka",
        "Donald Trump",
        "Maya",
        "Vic Cyberpunk",
    }


def test_voice_discovery_continues_when_one_compatibility_source_fails(tmp_path, monkeypatch) -> None:
    broken_dir = tmp_path / "broken"
    valid_dir = tmp_path / "valid"
    valid_dir.mkdir()
    (valid_dir / "Maya.wav").write_bytes(b"voice-audio")
    sources = [
        (broken_dir, broken_dir / "voice_clones.json"),
        (valid_dir, valid_dir / "voice_clones.json"),
    ]
    original_audio_files = voice_discovery._audio_files

    monkeypatch.setattr(voice_discovery, "voice_clone_sources", lambda: sources)

    def sometimes_fail(path: Path) -> list[Path]:
        if path == broken_dir:
            raise PermissionError("source unavailable")
        return original_audio_files(path)

    monkeypatch.setattr(voice_discovery, "_audio_files", sometimes_fail)

    assets = voice_discovery.discover_voice_clone_assets()

    assert [asset.metadata["profile_name"] for asset in assets] == ["Maya"]


def test_asset_library_keeps_voice_clones_when_an_unrelated_index_fails(tmp_path, monkeypatch) -> None:
    clone_dir = tmp_path / "voice_clones"
    clone_dir.mkdir()
    (clone_dir / "Maya.wav").write_bytes(b"voice-audio")
    monkeypatch.setenv("OMNIX_VOICE_CLONES_DIR", str(clone_dir))

    store = SharedAssetStore(tmp_path / "assets" / "manifest.json")

    def broken_image_index():
        raise RuntimeError("image index unavailable")

    monkeypatch.setattr(store, "preview_image_manifest_import", broken_image_index)

    assets = store.list_assets().assets
    voices = [asset for asset in assets if asset.type == AssetType.VOICE_PROFILE]

    assert len(voices) == 1
    assert voices[0].metadata["profile_name"] == "Maya"
