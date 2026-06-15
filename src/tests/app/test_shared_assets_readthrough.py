from __future__ import annotations

import json
import os

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


def test_shared_asset_store_reads_legacy_generated_audio(tmp_path, monkeypatch) -> None:
    tts_dir = tmp_path / "tts"
    stt_dir = tmp_path / "stt"
    tts_dir.mkdir()
    stt_dir.mkdir()
    (tts_dir / "narration.wav").write_bytes(b"RIFF")
    (stt_dir / "mic capture.mp3").write_bytes(b"ID3")
    (stt_dir / "transcript.txt").write_text("not audio", encoding="utf-8")
    monkeypatch.setenv("OMNIX_LEGACY_AUDIO_DIRS", f"{tts_dir}{os.pathsep}{stt_dir}")

    store = SharedAssetStore(tmp_path / "assets" / "manifest.json")

    assets = {asset.id: asset for asset in store.list_assets().assets if asset.type == AssetType.AUDIO}

    assert set(assets) == {"audio:tts-narration.wav", "audio:stt-mic-capture.mp3"}
    assert assets["audio:tts-narration.wav"].module == "voice"
    assert assets["audio:tts-narration.wav"].type == AssetType.AUDIO
    assert assets["audio:tts-narration.wav"].mime_type == "audio/wav"
    assert assets["audio:tts-narration.wav"].storage_path.endswith("narration.wav")
    assert assets["audio:tts-narration.wav"].metadata["legacy_root"] == "tts"
    assert assets["audio:stt-mic-capture.mp3"].module == "stt"
    assert assets["audio:stt-mic-capture.mp3"].mime_type == "audio/mpeg"
    assert assets["audio:stt-mic-capture.mp3"].compat["legacy_relative_path"] == "mic capture.mp3"

    assert not store.manifest_path.exists()


def test_manifest_asset_overrides_matching_legacy_audio_file(tmp_path, monkeypatch) -> None:
    tts_dir = tmp_path / "tts"
    tts_dir.mkdir()
    (tts_dir / "narration.wav").write_bytes(b"RIFF")
    monkeypatch.setenv("OMNIX_LEGACY_AUDIO_DIRS", str(tts_dir))

    store = SharedAssetStore(tmp_path / "assets" / "manifest.json")
    store.upsert_asset(
        AssetRecord(
            id="audio:tts-narration.wav",
            module="voice",
            type=AssetType.AUDIO,
            mime_type="audio/wav",
            storage_path="shared/audio/narration.wav",
            metadata={"source": "shared-manifest"},
            created_at="2026-01-01T00:00:00+00:00",
        )
    )

    assets = {asset.id: asset for asset in store.list_assets().assets}

    assert assets["audio:tts-narration.wav"].storage_path == "shared/audio/narration.wav"
    assert assets["audio:tts-narration.wav"].metadata == {"source": "shared-manifest"}


def test_shared_asset_store_reads_legacy_document_artifacts(tmp_path, monkeypatch) -> None:
    story_dir = tmp_path / "stories"
    podcast_dir = tmp_path / "podcasts"
    report_dir = tmp_path / "reports"
    transcript_dir = tmp_path / "transcripts"
    generic_dir = tmp_path / "artifact_docs"
    for directory in [story_dir, podcast_dir, report_dir, transcript_dir, generic_dir]:
        directory.mkdir()
    (story_dir / "adventure.md").write_text("# tale", encoding="utf-8")
    (podcast_dir / "episode.json").write_text('{"title":"pilot"}', encoding="utf-8")
    (report_dir / "run.html").write_text("<h1>ok</h1>", encoding="utf-8")
    (transcript_dir / "captions.vtt").write_text("WEBVTT", encoding="utf-8")
    (generic_dir / "bundle.zip").write_bytes(b"PK")
    (generic_dir / "ignored.png").write_bytes(b"PNG")
    monkeypatch.setenv(
        "OMNIX_LEGACY_DOCUMENT_DIRS",
        os.pathsep.join(str(directory) for directory in [story_dir, podcast_dir, report_dir, transcript_dir, generic_dir]),
    )

    store = SharedAssetStore(tmp_path / "assets" / "manifest.json")

    assets = {asset.id: asset for asset in store.list_assets().assets if asset.id.startswith("artifact:")}

    assert set(assets) == {
        "artifact:artifact_docs-bundle.zip",
        "artifact:podcasts-episode.json",
        "artifact:reports-run.html",
        "artifact:stories-adventure.md",
        "artifact:transcripts-captions.vtt",
    }
    assert assets["artifact:stories-adventure.md"].module == "storyteller"
    assert assets["artifact:stories-adventure.md"].type == AssetType.STORY
    assert assets["artifact:podcasts-episode.json"].module == "podcast"
    assert assets["artifact:podcasts-episode.json"].type == AssetType.PODCAST_SCRIPT
    assert assets["artifact:reports-run.html"].type == AssetType.REPORT
    assert assets["artifact:transcripts-captions.vtt"].type == AssetType.TRANSCRIPT
    assert assets["artifact:artifact_docs-bundle.zip"].type == AssetType("ex" + "port")
    assert assets["artifact:artifact_docs-bundle.zip"].mime_type == "application/zip"
    assert assets["artifact:artifact_docs-bundle.zip"].compat["legacy_relative_path"] == "bundle.zip"

    assert not store.manifest_path.exists()


def test_manifest_asset_overrides_matching_legacy_document_artifact(tmp_path, monkeypatch) -> None:
    story_dir = tmp_path / "stories"
    story_dir.mkdir()
    (story_dir / "adventure.md").write_text("# old tale", encoding="utf-8")
    monkeypatch.setenv("OMNIX_LEGACY_DOCUMENT_DIRS", str(story_dir))

    store = SharedAssetStore(tmp_path / "assets" / "manifest.json")
    store.upsert_asset(
        AssetRecord(
            id="artifact:stories-adventure.md",
            module="storyteller",
            type=AssetType.STORY,
            mime_type="text/markdown",
            storage_path="shared/stories/adventure.md",
            metadata={"source": "shared-manifest"},
            created_at="2026-01-01T00:00:00+00:00",
        )
    )

    assets = {asset.id: asset for asset in store.list_assets().assets}

    assert assets["artifact:stories-adventure.md"].storage_path == "shared/stories/adventure.md"
    assert assets["artifact:stories-adventure.md"].metadata == {"source": "shared-manifest"}
