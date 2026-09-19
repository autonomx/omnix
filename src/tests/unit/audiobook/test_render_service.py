from __future__ import annotations

import base64
import io
import wave

import pytest

from app.audiobook.render_service import RenderFailure, decode_pcm_wav, higher_priority_tts_pending
from app.persistence.tenant import local_tenant_context


def _wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(b"\x00\x00" * 160)
    return buffer.getvalue()


def test_only_valid_lossless_provider_audio_is_accepted() -> None:
    content = _wav()
    audio, duration, rate = decode_pcm_wav({"success": True, "audio": base64.b64encode(content).decode()})
    assert audio == content
    assert duration == pytest.approx(0.01)
    assert rate == 16000
    with pytest.raises(RenderFailure):
        decode_pcm_wav({"success": False, "is_fallback": True, "audio": base64.b64encode(content).decode()})
    with pytest.raises(RenderFailure):
        decode_pcm_wav({"success": True, "audio": base64.b64encode(b"bad").decode()})


class _Connection:
    def __init__(self, pending: bool) -> None:
        self.pending = pending
        self.params = None

    def execute(self, _sql, params):
        self.params = params
        return self

    def fetchone(self):
        return (self.pending,)


def test_offline_priority_check_includes_realtime_and_preview() -> None:
    connection = _Connection(True)
    assert higher_priority_tts_pending(connection, local_tenant_context())
    assert "gpu:tts:realtime" in connection.params[1]
    assert "gpu:tts:preview" in connection.params[1]
