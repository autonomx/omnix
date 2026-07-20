import base64
import json
from types import SimpleNamespace
from typing import Any

import app.shared as shared
from app.jobs import voice_inline


class _FakeSttProvider:
    provider_name = "parakeet"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def transcribe(self, audio_path: str, language: str | None = None) -> dict[str, object]:
        self.calls.append((audio_path, language))
        return {
            "success": True,
            "text": "The exact words spoken in the reference sample.",
            "segments": [],
        }


def test_clone_job_generates_and_persists_stt_reference_transcript(tmp_path, monkeypatch) -> None:
    provider = _FakeSttProvider()
    captured: dict[str, Any] = {}

    monkeypatch.setattr(voice_inline, "_voice_clone_dir", lambda: tmp_path)
    monkeypatch.setattr(shared, "get_stt_provider", lambda provider_name=None: provider)
    monkeypatch.setattr(voice_inline, "_upsert_asset", lambda asset: captured.setdefault("asset", asset))
    monkeypatch.setattr(
        voice_inline,
        "_upsert_legacy_voice_manifest",
        lambda voice_id, profile_name, payload, clone_path: captured.setdefault("manifest_payload", payload),
    )

    job = SimpleNamespace(
        id="job:auto-transcript",
        input_payload={
            "profile_name": "Maya Test",
            "sample_audio_base64": base64.b64encode(b"sample-audio").decode("ascii"),
            "source_file_name": "maya.wav",
            "language": "English",
            "generate_transcript": True,
            "stt_provider_id": "parakeet",
        },
    )

    voice_inline._execute_clone_job(job)

    sidecar = json.loads((tmp_path / "Maya-Test.json").read_text(encoding="utf-8"))
    assert sidecar["ref_text"] == "The exact words spoken in the reference sample."
    assert sidecar["transcript_source"] == "stt"
    assert sidecar["stt_provider"] == "parakeet"
    assert provider.calls == [(str(tmp_path / "Maya-Test.wav"), "English")]

    asset = captured["asset"]
    assert asset.metadata["reference_text"] == sidecar["ref_text"]
    assert asset.metadata["transcript_path"] == str(tmp_path / "Maya-Test.json")
    assert captured["manifest_payload"]["reference_text"] == sidecar["ref_text"]


def test_manual_reference_transcript_takes_precedence_over_stt(tmp_path, monkeypatch) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(voice_inline, "_voice_clone_dir", lambda: tmp_path)
    monkeypatch.setattr(
        shared,
        "get_stt_provider",
        lambda provider_name=None: (_ for _ in ()).throw(AssertionError("STT should not be loaded")),
    )
    monkeypatch.setattr(voice_inline, "_upsert_asset", lambda asset: asset)
    monkeypatch.setattr(
        voice_inline,
        "_upsert_legacy_voice_manifest",
        lambda voice_id, profile_name, payload, clone_path: captured.setdefault("manifest_payload", payload),
    )

    job = SimpleNamespace(
        id="job:manual-transcript",
        input_payload={
            "profile_name": "Manual Voice",
            "sample_audio_base64": base64.b64encode(b"sample-audio").decode("ascii"),
            "source_file_name": "manual.wav",
            "reference_text": "A carefully corrected reference transcript.",
            "generate_transcript": True,
        },
    )

    voice_inline._execute_clone_job(job)

    sidecar = json.loads((tmp_path / "Manual-Voice.json").read_text(encoding="utf-8"))
    assert sidecar["ref_text"] == "A carefully corrected reference transcript."
    assert sidecar["transcript_source"] == "manual"
    assert captured["manifest_payload"]["transcript_source"] == "manual"


def test_transcribe_sample_job_returns_transcript_without_creating_clone(tmp_path, monkeypatch) -> None:
    provider = _FakeSttProvider()
    monkeypatch.setattr(shared, "get_stt_provider", lambda provider_name=None: provider)

    job = SimpleNamespace(
        id="job:preview-transcript",
        input_payload={
            "sample_audio_base64": base64.b64encode(b"sample-audio").decode("ascii"),
            "source_file_name": "sofia2.wav",
            "language": "English",
            "stt_provider_id": "parakeet",
        },
    )

    result = voice_inline._execute_transcribe_sample_job(job)

    assert result["content"] == "The exact words spoken in the reference sample."
    assert result["output_refs"] == [
        {
            "type": "transcript",
            "title": "Reference transcript",
            "content": "The exact words spoken in the reference sample.",
            "provider_id": "parakeet",
        }
    ]
    assert len(provider.calls) == 1
    assert provider.calls[0][1] == "English"
