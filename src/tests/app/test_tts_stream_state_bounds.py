from __future__ import annotations

from app.observability import tts_stream_diagnostics as streams


def test_active_tts_stream_registry_is_bounded_expiring_and_clearable(monkeypatch) -> None:
    now = 100.0
    monkeypatch.setattr(streams, "_stream_now", lambda: now)
    monkeypatch.setattr(streams, "_MAX_ACTIVE_STREAMS", 2)
    monkeypatch.setattr(streams, "_ACTIVE_STREAM_TTL_SECONDS", 10.0)
    monkeypatch.setattr(streams, "stream_log", lambda *_args, **_kwargs: None)
    streams.clear_active_streams()

    streams.begin_stream("first")
    streams.begin_stream("second")
    streams.begin_stream("third")
    assert set(streams.active_streams_snapshot()) == {"second", "third"}

    now += 11.0
    assert streams.active_streams_snapshot() == {}

    streams.begin_stream("clear-me")
    streams.clear_active_streams()
    assert streams.active_streams_snapshot() == {}
