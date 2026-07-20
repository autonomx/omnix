from __future__ import annotations

import wave
from pathlib import Path

from fastapi.testclient import TestClient

from app.gateway.main import create_gateway_app


class EmptyJobStore:
    def list_events(self, after_id: int, limit: int):
        return []


def _write_wav(path: Path, sample_rate: int = 24_000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes((b"\x00\x00\x10\x00") * 80)


def test_live_voice_cue_manifest_discovers_safe_voice_pack(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_LIVE_VOICE_CUE_ROOT", str(tmp_path))
    _write_wav(tmp_path / "Nate Fallout" / "hmm-v1.wav", 24_000)
    _write_wav(tmp_path / "Nate Fallout" / "inhale-v2.wav", 48_000)
    _write_wav(tmp_path / "Nate Fallout" / "not-a-cue.wav", 24_000)

    client = TestClient(create_gateway_app(job_store_factory=lambda: EmptyJobStore()))
    response = client.get("/api/voice/cues/Nate%20Fallout/manifest")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == 1
    assert payload["voice_id"] == "Nate Fallout"
    assert payload["available"] is True
    assert [(asset["cue_id"], asset["variant_id"], asset["sample_rate"]) for asset in payload["assets"]] == [
        ("hmm", "hmm-v1", 24_000),
        ("inhale", "inhale-v2", 48_000),
    ]
    assert payload["assets"][0]["url"].startswith("/api/voice/cues/Nate%20Fallout/")
    assert len(payload["assets"][0]["sha256"]) == 64


def test_live_voice_cue_file_uses_etag_and_blocks_invalid_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_LIVE_VOICE_CUE_ROOT", str(tmp_path))
    _write_wav(tmp_path / "Jinx" / "mhm-v1.wav")
    client = TestClient(create_gateway_app(job_store_factory=lambda: EmptyJobStore()))

    first = client.get("/api/voice/cues/Jinx/mhm/mhm-v1.wav")
    assert first.status_code == 200
    assert first.headers["content-type"].startswith("audio/wav")
    assert first.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert first.headers["x-content-type-options"] == "nosniff"

    cached = client.get(
        "/api/voice/cues/Jinx/mhm/mhm-v1.wav",
        headers={"If-None-Match": first.headers["etag"]},
    )
    assert cached.status_code == 304
    assert client.get("/api/voice/cues/Jinx/hmm/mhm-v1.wav").status_code == 404
    assert client.get("/api/voice/cues/../manifest").status_code in {400, 404}


def test_missing_voice_pack_returns_explicit_unavailable_manifest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_LIVE_VOICE_CUE_ROOT", str(tmp_path))
    client = TestClient(create_gateway_app(job_store_factory=lambda: EmptyJobStore()))

    response = client.get("/api/voice/cues/Maya/manifest")

    assert response.status_code == 200
    assert response.json() == {
        "schema_version": 1,
        "voice_id": "Maya",
        "available": False,
        "assets": [],
    }
