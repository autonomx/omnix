"""The feature-neutral TTS helper's stream: live speech's pieces as PCM16, with the caller's chunk size and decode."""
from __future__ import annotations

import numpy as np


def test_a_stream_is_pcm16_pieces_with_the_callers_decode_and_is_closed(monkeypatch) -> None:
    from app.providers import tts_service

    calls: list[dict] = []
    closed: list[bool] = []

    class Engine:
        def generate_audio_stream(self, **kwargs):
            calls.append(kwargs)

            def chunks():
                try:
                    yield np.array([0.5, -0.5], dtype=np.float32), 24000, {}
                    yield np.array([0.25], dtype=np.float32), 24000, {}
                finally:
                    closed.append(True)

            return chunks()

    monkeypatch.setattr("app.providers.service.get_tts_provider", lambda name=None: Engine())
    pieces = list(tts_service.stream_audio_pcm16("Hello.", speaker="default",
                                                 generation={"chunk_size": 8, "parity_mode": False}))
    assert [(len(pcm), rate) for pcm, rate in pieces] == [(4, 24000), (2, 24000)]
    assert np.frombuffer(pieces[0][0], dtype="<i2").tolist() == [16383, -16383]  # scaled by 32767
    assert {key: calls[0][key] for key in ("text", "speaker", "language", "chunk_size", "parity_mode")} == {
        "text": "Hello.", "speaker": "default", "language": "en", "chunk_size": 8, "parity_mode": False}
    assert closed == [True]
