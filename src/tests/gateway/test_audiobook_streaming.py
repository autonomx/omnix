from __future__ import annotations

from tests.support.routers import effective_routes

import math
import wave
from io import BytesIO

from fastapi.testclient import TestClient

from app.audiobook.streaming import AUDIOBOOK_SAMPLE_RATE
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
    from app.audiobook import streaming as audiobook_streaming

    def fake_generate_audio_bytes(text: str, *, speaker: str, payload: dict):
        return _test_wav(), {"sample_rate": AUDIOBOOK_SAMPLE_RATE, "speaker": speaker, "text": text}

    monkeypatch.setattr(audiobook_streaming, "generate_audio_bytes", fake_generate_audio_bytes)
    client = TestClient(
        create_gateway_app(),
        base_url="http://localhost",
        headers={"X-Omnix-Client": "test"},
    )

    with client.websocket_connect(
        "/ws/audiobook", headers={"Host": "localhost"}
    ) as websocket:
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


def test_story_audio_keeps_abbreviations_and_quoted_dialogue_together() -> None:
    from app.audiobook.streaming import _sentence_segments_from_start_message

    segments = _sentence_segments_from_start_message({
        "text": 'Dr. Vale waited. "Follow me." she said. The door opened.',
    })
    assert [segment["text"] for segment in segments] == [
        "Dr. Vale waited.", '"Follow me." she said.', "The door opened.",
    ]


def test_gateway_keeps_current_audiobook_and_story_streaming_routes() -> None:
    paths = {str(getattr(route, "path", "")) for route in effective_routes(create_gateway_app())}
    assert "/api/audiobook/projects" in paths
    assert "/ws/audiobook" in paths
    assert "/api/audiobook/upload" not in paths
    assert "/api/audiobook/generate" not in paths
