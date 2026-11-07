"""Smart Turn: the STT service judges from the voice whether a pause ends the turn, and says so with Parakeet's signal."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import numpy as np

from app.providers import nemotron_eou_live_websocket as live
from app.providers import smart_turn
from app.providers.nemotron_eou_streaming import HybridUpdate


class _Session:
    def __init__(self, value: float) -> None:
        self.value = value
        self.features: list[np.ndarray] = []

    def run(self, _outputs, inputs):
        self.features.append(inputs["input_features"])
        return [np.array([[self.value]], dtype=np.float32)]


def _model(value: float) -> tuple[smart_turn._SmartTurn, _Session]:
    model = smart_turn._SmartTurn()
    session = _Session(value)
    model._loaded = True
    model._session = session
    model._extractor = lambda audio, **_kwargs: SimpleNamespace(
        input_features=np.full((1, 80, 800), float(len(audio)), dtype=np.float32),
    )
    return model, session


def test_the_last_eight_seconds_are_judged_with_silence_padded_before_them() -> None:
    model, session = _model(0.97)
    two_seconds = np.full(2 * 16_000, 1000, dtype="<i2").tobytes()

    assert abs(model.probability(two_seconds) - 0.97) < 1e-6
    assert session.features[0][0, 0, 0] == 8 * 16_000  # padded to the window
    twelve_seconds = np.zeros(12 * 16_000, dtype="<i2").tobytes()
    model.probability(twelve_seconds)
    assert session.features[1][0, 0, 0] == 8 * 16_000  # cut to the last 8 s


def test_without_the_model_turns_keep_the_fixed_wait(monkeypatch) -> None:
    # The service reads only the installed copy: tests and a fresh install never download it from here.
    monkeypatch.setattr(smart_turn, "_cached_model_file", lambda: (_ for _ in ()).throw(FileNotFoundError("not installed")))
    model = smart_turn._SmartTurn()
    monkeypatch.setattr(smart_turn, "_MODEL", model)

    assert smart_turn.turn_complete_probability(b"\x00\x00" * 1600) is None
    assert model.load() is False


def test_parakeets_signal_carries_the_verdict(monkeypatch) -> None:
    sent: list[dict] = []

    async def capture(_websocket, _lock, payload):
        sent.append(payload)
        return True

    monkeypatch.setattr(live, "_safe_send", capture)
    monkeypatch.setattr(live, "turn_complete_probability", lambda pcm: 0.9731 if pcm else None)
    manager = SimpleNamespace(
        feed_chunk_samples=320,
        feed=lambda _segment_id, _payload: HybridUpdate(
            transcript="go tonight", transcript_changed=False, eou=True, nemotron_ms=1.0, eou_ms=1.0,
        ),
    )
    segment = live.HybridSegment(segment_id="segment-1", sequence=1, capture_start_sample=0, primary_start_sample=0)
    segment.primary_audio.extend(b"\x10\x00" * 640)
    segment.stream_pending.extend(b"\x10\x00" * 320)

    asyncio.run(live._drain_stream_audio(segment, manager, websocket=None, send_lock=asyncio.Lock()))

    candidate = next(payload for payload in sent if payload["type"] == "endpoint_candidate")
    assert candidate["turnComplete"] == 0.973
    assert candidate["probability"] == 1.0


def test_without_a_verdict_the_signal_is_as_before(monkeypatch) -> None:
    sent: list[dict] = []

    async def capture(_websocket, _lock, payload):
        sent.append(payload)
        return True

    monkeypatch.setattr(live, "_safe_send", capture)
    monkeypatch.setattr(live, "turn_complete_probability", lambda _pcm: None)
    manager = SimpleNamespace(
        feed_chunk_samples=320,
        feed=lambda _segment_id, _payload: HybridUpdate(
            transcript="", transcript_changed=False, eou=True, nemotron_ms=1.0, eou_ms=1.0,
        ),
    )
    segment = live.HybridSegment(segment_id="segment-1", sequence=1, capture_start_sample=0, primary_start_sample=0)
    segment.stream_pending.extend(b"\x10\x00" * 320)

    asyncio.run(live._drain_stream_audio(segment, manager, websocket=None, send_lock=asyncio.Lock()))

    candidate = next(payload for payload in sent if payload["type"] == "endpoint_candidate")
    assert "turnComplete" not in candidate
