"""How like the voice's own clip a live take sounds, asked of the speech service's speaker model."""
from __future__ import annotations

import io
import wave
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.platform.live_voice.speech.voice_likeness import VoiceLikeness

PCM = (np.full(24_000, 0.1, dtype=np.float32) * 32767).astype("<i2").tobytes()


def _clip(tmp_path: Path) -> Path:
    path = tmp_path / "clip.wav"
    path.write_bytes(b"the clip's bytes")
    return path


def _likeness(tmp_path: Path, vectors: dict[bytes, list[float]], calls: list[bytes] | None = None) -> VoiceLikeness:
    def embed(payload: bytes, filename: str) -> list[float] | None:
        if calls is not None:
            calls.append(payload)
        return vectors.get(payload, vectors.get(b"take"))

    return VoiceLikeness("Abhishek", embed=embed, reference=lambda _speaker: str(_clip(tmp_path)))


def test_a_take_is_scored_against_the_voices_own_clip(tmp_path: Path) -> None:
    likeness = _likeness(tmp_path, {b"the clip's bytes": [1.0, 0.0], b"take": [0.6, 0.8]})

    assert likeness.score([PCM], 24_000) == pytest.approx(0.6)


def test_vectors_need_not_be_normalized(tmp_path: Path) -> None:
    likeness = _likeness(tmp_path, {b"the clip's bytes": [5.0, 0.0], b"take": [3.0, 4.0]})

    assert likeness.score([PCM], 24_000) == pytest.approx(0.6)


def test_the_clip_is_embedded_once_for_a_call(tmp_path: Path) -> None:
    calls: list[bytes] = []
    likeness = _likeness(tmp_path, {b"the clip's bytes": [1.0, 0.0], b"take": [1.0, 0.0]}, calls)

    likeness.score([PCM], 24_000)
    likeness.score([PCM], 24_000)

    assert calls.count(b"the clip's bytes") == 1
    assert len(calls) == 3


def test_a_take_is_sent_as_a_wav_at_its_own_rate(tmp_path: Path) -> None:
    calls: list[bytes] = []
    _likeness(tmp_path, {b"the clip's bytes": [1.0, 0.0], b"take": [1.0, 0.0]}, calls).score([PCM[:1000], PCM[1000:]], 24_000)

    with wave.open(io.BytesIO(calls[-1])) as sent:
        assert (sent.getframerate(), sent.getnchannels(), sent.getsampwidth()) == (24_000, 1, 2)
        assert sent.readframes(sent.getnframes()) == PCM


@pytest.mark.parametrize("failure", ["embed_raises", "embed_none", "no_reference", "reference_raises", "zero_vector"])
def test_any_failure_means_no_score_never_an_error(tmp_path: Path, failure: str) -> None:
    def embed(payload: bytes, _filename: str) -> list[float] | None:
        if failure == "embed_raises":
            raise RuntimeError("service down")
        if failure == "embed_none":
            return None
        return [0.0, 0.0] if failure == "zero_vector" else [1.0, 0.0]

    def reference(_speaker: str) -> str | None:
        if failure == "reference_raises":
            raise RuntimeError("no assets")
        return None if failure == "no_reference" else str(_clip(tmp_path))

    assert VoiceLikeness("Abhishek", embed=embed, reference=reference).score([PCM], 24_000) is None


def test_a_failed_clip_is_tried_again_on_the_next_phrase(tmp_path: Path) -> None:
    answers: list[Any] = [None, [1.0, 0.0], [1.0, 0.0]]
    likeness = VoiceLikeness("Abhishek", embed=lambda _payload, _name: answers.pop(0), reference=lambda _speaker: str(_clip(tmp_path)))

    assert likeness.score([PCM], 24_000) is None
    assert likeness.score([PCM], 24_000) == pytest.approx(1.0)


def _service(monkeypatch, *, missing: bool = False):
    from services.stt import timed_transcription as timed

    def get() -> Any:
        if missing:
            raise timed.TimedTranscriptionUnavailable("TitaNet speaker embeddings is not installed")
        return object()

    monkeypatch.setattr(timed.SPEAKERS, "get", get)
    monkeypatch.setattr(timed, "_embedding", lambda _model, piece: np.array([0.25, len(piece) / 16_000], dtype=np.float32))
    app = FastAPI()
    timed.install_timed_transcription_routes(app, decode=lambda payload, _name: (payload, len(payload) / 32_000), live_active=lambda: True)
    return TestClient(app)


def test_the_service_returns_a_recordings_embedding(monkeypatch) -> None:
    response = _service(monkeypatch).post("/speaker/embedding", files={"file": ("take.wav", b"\x00\x00" * 16_000)})

    assert response.status_code == 200
    assert response.json() == {"ok": True, "embedding": [0.25, 1.0]}


def test_the_service_says_when_the_model_is_not_there(monkeypatch) -> None:
    response = _service(monkeypatch, missing=True).post("/speaker/embedding", files={"file": ("take.wav", b"\x00\x00" * 16_000)})

    assert response.json()["ok"] is False
    assert response.json()["code"] == "model_unavailable"


def test_the_service_refuses_an_empty_recording(monkeypatch) -> None:
    assert _service(monkeypatch).post("/speaker/embedding", files={"file": ("take.wav", b"")}).status_code == 400
