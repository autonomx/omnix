from __future__ import annotations

import json
from pathlib import Path

from app.assets import canonical_voice_clones


def test_lowercase_voice_file_uses_case_sensitive_manifest_speaker(
    tmp_path: Path,
    monkeypatch,
) -> None:
    resources = tmp_path / "resources"
    clone_root = resources / "voice_clones"
    clone_root.mkdir(parents=True)
    (clone_root / "jinx.wav").write_bytes(b"RIFF-jinx")
    (clone_root / "voice_clones.json").write_text(
        json.dumps(
            {
                "Jinx": {
                    "speaker": "default",
                    "language": "en",
                    "voice_clone_id": "Jinx",
                    "has_audio": True,
                    "is_preloaded": True,
                    "gender": "neutral",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(canonical_voice_clones, "resources_root", lambda: resources)

    assets = canonical_voice_clones.discover_canonical_voice_clone_assets()

    assert len(assets) == 1
    asset = assets[0]
    assert asset.id == "voice-cloning:jinx"
    assert asset.metadata["profile_name"] == "Jinx"
    assert asset.metadata["voice_id"] == "Jinx"
    assert asset.metadata["voice_clone_id"] == "Jinx"
    assert asset.metadata["resolved_from_voice_manifest"] is True


def test_canonical_voice_without_manifest_keeps_filename_identity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    resources = tmp_path / "resources"
    clone_root = resources / "voice_clones"
    clone_root.mkdir(parents=True)
    (clone_root / "Morgan.wav").write_bytes(b"RIFF-morgan")
    monkeypatch.setattr(canonical_voice_clones, "resources_root", lambda: resources)

    assets = canonical_voice_clones.discover_canonical_voice_clone_assets()

    assert len(assets) == 1
    asset = assets[0]
    assert asset.id == "voice-cloning:Morgan"
    assert asset.metadata["voice_clone_id"] == "Morgan"
    assert asset.metadata["resolved_from_voice_manifest"] is False
