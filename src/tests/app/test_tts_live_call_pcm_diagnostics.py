from types import SimpleNamespace

from app.gateway import tts_live_call_pcm_diagnostics as diagnostics


def _capture_events(monkeypatch):
    events = []
    monkeypatch.setattr(
        diagnostics,
        "stream_log",
        lambda stream_id, source, event, **details: events.append(
            (stream_id, source, event, details)
        ),
    )
    return events


def test_measured_pcm_converter_logs_first_conversion_only(monkeypatch) -> None:
    events = _capture_events(monkeypatch)
    diagnostics._THREAD_STATE.conversion_index = 0
    audio = SimpleNamespace(
        shape=(3, 1),
        dtype="float32",
        device="cuda:0",
    )
    converter = diagnostics.measured_pcm_converter(lambda _audio: b"\x00\x00" * 3)

    assert converter(audio) == b"\x00\x00" * 3
    assert converter(audio) == b"\x00\x00" * 3

    assert len(events) == 1
    stream_id, source, event, details = events[0]
    assert stream_id == "gateway-live-tts-pcm-conversion"
    assert source == "provider"
    assert event == "first_pcm_conversion_completed"
    assert details["pcm_samples"] == 3
    assert details["input_shape"] == [3, 1]
    assert details["input_device"] == "cuda:0"


def test_measured_pcm_block_streamer_reports_first_audible_block(monkeypatch) -> None:
    events = _capture_events(monkeypatch)

    def fake_streamer(chunks, *, block_samples):
        source = list(chunks)
        assert len(source) == 2
        assert block_samples == 4
        yield b"\x01\x00" * 4, 24_000, {"chunk_index": 1}
        yield b"\x02\x00" * 4, 24_000, {"chunk_index": 1}

    streamer = diagnostics.measured_pcm_block_streamer(fake_streamer)
    blocks = list(
        streamer(
            iter(
                [
                    (b"\x00\x00" * 4, 24_000, {"chunk_index": 0}),
                    (b"\x01\x00" * 8, 24_000, {"chunk_index": 1}),
                ]
            ),
            block_samples=4,
        )
    )

    assert len(blocks) == 2
    assert len(events) == 1
    stream_id, source, event, details = events[0]
    assert stream_id == "gateway-live-tts-pcm-conversion"
    assert source == "provider"
    assert event == "first_audible_pcm_block_ready"
    assert details["raw_chunks_before_audible_block"] == 2
    assert details["block_samples"] == 4
    assert details["sample_rate"] == 24_000
    assert details["raw_to_audible_block_ms"] >= 0