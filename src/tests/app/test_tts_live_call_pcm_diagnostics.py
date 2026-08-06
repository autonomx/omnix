from types import SimpleNamespace

from app.gateway import tts_live_call_pcm_diagnostics as diagnostics


def test_measured_pcm_converter_logs_first_conversion_only(monkeypatch) -> None:
    events = []
    monkeypatch.setattr(
        diagnostics,
        "stream_log",
        lambda stream_id, source, event, **details: events.append(
            (stream_id, source, event, details)
        ),
    )
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
