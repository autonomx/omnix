"""The macOS speech service: energy endpointing and the live protocol over a stand-in model (DT-8.2).

Parakeet-MLX itself needs Apple Silicon; here a fake transcriber stands in, so the protocol the gateway and the
browser rely on (ready, session_ready, audio_buffered, partial, endpoint_candidate, result_available) is checked on
any machine.
"""
from __future__ import annotations

import base64
import secrets
import sys

import numpy as np
import pytest

sys.path.insert(0, "src")

from services.stt.energy_endpointing import SAMPLE_RATE, EnergyEndpointer  # noqa: E402


def _tone(seconds: float, amplitude: float = 0.3) -> bytes:
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    return (np.sin(2 * np.pi * 220 * t) * amplitude * 32767).astype("<i2").tobytes()


def _noise(seconds: float, amplitude: float = 0.003) -> bytes:
    rng = np.random.default_rng(7)
    return (rng.standard_normal(int(seconds * SAMPLE_RATE)) * amplitude * 32767).astype("<i2").tobytes()


def test_speech_then_silence_ends_the_utterance_once() -> None:
    endpointer = EnergyEndpointer()
    assert not endpointer.feed(_noise(0.5))
    assert not endpointer.feed(_tone(1.0))
    assert not endpointer.feed(_noise(0.4))  # a short pause is not the end
    assert endpointer.feed(_noise(0.5))
    assert not endpointer.feed(_noise(1.0))  # once per utterance
    assert not endpointer.feed(_tone(0.6))
    assert endpointer.feed(_noise(0.8))  # new speech re-arms it


def test_room_noise_alone_is_never_an_utterance() -> None:
    endpointer = EnergyEndpointer()
    assert not any(endpointer.feed(_noise(0.2)) for _ in range(20))


def test_a_click_shorter_than_speech_does_not_count() -> None:
    endpointer = EnergyEndpointer()
    assert not endpointer.feed(_tone(0.1) + _noise(1.5))


def test_odd_chunk_sizes_are_handled() -> None:
    endpointer = EnergyEndpointer()
    audio = _tone(1.0) + _noise(1.0)
    ended = [endpointer.feed(audio[start:start + 777]) for start in range(0, len(audio), 777)]
    assert sum(ended) == 1


class _FakeParakeet:
    def __init__(self) -> None:
        self.loaded = False
        self.calls = 0

    def load(self) -> None:
        self.loaded = True

    def transcribe_pcm16(self, pcm16: bytes) -> str:
        self.calls += 1
        seconds = len(pcm16) / 2 / SAMPLE_RATE
        return f"heard {seconds:.1f} seconds" if seconds >= 0.5 else ""


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient

    from services.stt.parakeet_mlx_server import create_app

    token = secrets.token_urlsafe(32)
    monkeypatch.setenv("OMNIX_SERVICE_TOKEN", token)
    model = _FakeParakeet()
    app = create_app(model, preload=True)
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        yield test_client, token, model


def test_health_reports_the_model_and_needs_no_token(client) -> None:
    test_client, _, model = client
    body = test_client.get("/health").json()
    assert body["provider"] == "parakeet-mlx" and body["ok"] is model.loaded is True


def test_the_live_protocol_ends_the_utterance_and_returns_the_final_transcript(client) -> None:
    test_client, token, _ = client
    with test_client.websocket_connect("ws://127.0.0.1/ws/transcribe", headers={"X-Omnix-Service-Token": token}) as socket:
        ready = socket.receive_json()
        assert ready["type"] == "ready" and ready["protocol"] == "segmented-v1" and ready["sampleRate"] == 16000
        assert "authoritative_eou" in ready["capabilities"]
        socket.send_json({"type": "hello", "sessionId": "s1"})
        assert socket.receive_json()["type"] == "session_ready"
        audio = _noise(0.2) + _tone(1.2) + _noise(1.0)
        chunk = 3200
        chunks = range(0, len(audio), chunk)
        for offset in chunks:
            socket.send_json({"type": "audio", "segmentId": "seg-1", "sequence": 1, "sampleRate": 16000,
                              "data": base64.b64encode(audio[offset:offset + chunk]).decode()})
        socket.send_json({"type": "finalize", "segmentId": "seg-1", "sequence": 1})
        # The service answers in order: every chunk is acknowledged, partials and the endpoint follow the chunk
        # that produced them, and the final transcript comes after the finalize was queued.
        messages = [socket.receive_json()]
        while messages[-1]["type"] != "result_available":
            messages.append(socket.receive_json())
        kinds = [message["type"] for message in messages]
        assert kinds.count("audio_buffered") == len(chunks) and kinds[0] == "audio_buffered"
        assert "partial" in kinds
        assert kinds.index("endpoint_score") + 1 == kinds.index("endpoint_candidate") < kinds.index("finalize_queued")
        assert kinds[-2:] == ["finalize_queued", "result_available"]
        result = messages[-1]
        assert result["text"] == "heard 2.4 seconds" and result["segmentId"] == "seg-1"
        # A repeated finalize replays the same result.
        socket.send_json({"type": "finalize", "segmentId": "seg-1", "sequence": 1})
        assert socket.receive_json()["resultId"] == result["resultId"]


def test_an_endpoint_candidate_is_sent_after_speech_and_silence(client) -> None:
    test_client, token, _ = client
    with test_client.websocket_connect("ws://127.0.0.1/ws/transcribe", headers={"X-Omnix-Service-Token": token}) as socket:
        socket.receive_json()
        audio = _tone(1.0) + _noise(1.0)
        socket.send_json({"type": "audio", "segmentId": "seg-2", "sequence": 2, "sampleRate": 16000,
                          "data": base64.b64encode(audio).decode()})
        messages = [socket.receive_json() for _ in range(4)]
        assert [message["type"] for message in messages] == ["audio_buffered", "partial", "endpoint_score",
                                                              "endpoint_candidate"]
        assert messages[-1]["signal"] == "energy"


def test_a_wrong_sample_rate_is_refused(client) -> None:
    test_client, token, _ = client
    with test_client.websocket_connect("ws://127.0.0.1/ws/transcribe", headers={"X-Omnix-Service-Token": token}) as socket:
        socket.receive_json()
        socket.send_json({"type": "audio", "segmentId": "seg", "sequence": 1, "sampleRate": 48000, "data": ""})
        assert socket.receive_json()["errorCode"] == "sample_rate_mismatch"


def test_the_websocket_needs_the_service_token(client) -> None:
    from starlette.websockets import WebSocketDisconnect

    test_client, _, _ = client
    with pytest.raises(WebSocketDisconnect):
        with test_client.websocket_connect("ws://127.0.0.1/ws/transcribe") as socket:
            socket.receive_json()


def test_batch_transcription_takes_a_wav(client) -> None:
    import io
    import wave

    test_client, token, _ = client
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(_tone(1.0))
    response = test_client.post("/transcribe", headers={"X-Omnix-Service-Token": token, "X-Omnix-Client": "test"},
                                files={"file": ("a.wav", buffer.getvalue(), "audio/wav")})
    assert response.status_code == 200 and response.json()["text"] == "heard 1.0 seconds"
