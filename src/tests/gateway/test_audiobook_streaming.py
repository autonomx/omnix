from __future__ import annotations

import math
import wave
from io import BytesIO

from fastapi.testclient import TestClient

from app.gateway.audiobook_streaming import AUDIOBOOK_SAMPLE_RATE
from app.gateway.main import create_gateway_app


def _test_wav() -> bytes:
    sample_count = AUDIOBOOK_SAMPLE_RATE // 20
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(AUDIOBOOK_SAMPLE_RATE)
        frames = bytearray()
        for index in range(sample_count):
            value = int(32767 * 0.1 * math.sin(2 * math.pi * 220 * index / AUDIOBOOK_SAMPLE_RATE))
            frames.extend(value.to_bytes(2, byteorder="little", signed=True))
        wav_file.writeframes(bytes(frames))
    return buffer.getvalue()


def test_audiobook_websocket_streams_pcm(monkeypatch) -> None:
    from app.gateway import audiobook_streaming

    def fake_generate_audio_bytes(text: str, *, speaker: str, payload: dict):
        return _test_wav(), {"sample_rate": AUDIOBOOK_SAMPLE_RATE, "speaker": speaker, "text": text}

    monkeypatch.setattr(audiobook_streaming, "_generate_audio_bytes", fake_generate_audio_bytes)
    client = TestClient(create_gateway_app())

    with client.websocket_connect("/ws/audiobook") as websocket:
        websocket.send_json(
            {
                "type": "start",
                "job_id": "story-test",
                "segments": [{"speaker": "Narrator", "text": "Hello world."}],
                "voice_mapping": {"Narrator": "resources/voice_clones/Jinx.wav"},
                "default_voices": {"narrator": "resources/voice_clones/Jinx.wav"},
            }
        )

        assert websocket.receive_json() == {"type": "start", "total_segments": 1}
        assert websocket.receive_json()["type"] == "segment"
        pcm = websocket.receive_bytes()
        assert isinstance(pcm, bytes)
        assert len(pcm) > 0
        assert websocket.receive_json() == {"type": "done", "job_id": "story-test"}
