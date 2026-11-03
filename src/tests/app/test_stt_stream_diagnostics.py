"""The live recognizer's persistent log: what it received and returned, and never what was said."""
from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.observability import stt_stream_diagnostics
from app.providers import nemotron_eou_live_websocket as live_stt
from app.providers.nemotron_eou_live_websocket import install_nemotron_eou_websocket


class _Manager:
    """Enough of the model manager for a connection that never reaches a final, nor a full chunk to feed."""

    feed_chunk_samples = 16_000

    def release(self, _segment_id: str) -> None:
        return None


def _binary_frame(header: dict, pcm: bytes) -> bytes:
    encoded = json.dumps(header).encode("utf-8")
    return len(encoded).to_bytes(4, "little") + encoded + pcm


def test_a_connection_leaves_its_lifecycle_and_received_audio_in_the_log(monkeypatch) -> None:
    logged: list[tuple[str, dict]] = []
    monkeypatch.setattr(live_stt, "stt_stream_log", lambda event, **fields: logged.append((event, fields)))
    app = FastAPI()
    install_nemotron_eou_websocket(app, _Manager())

    with TestClient(app).websocket_connect("/ws/transcribe") as socket:
        socket.receive_json()  # ready
        socket.send_json({"type": "hello", "sessionId": "stt-session-1"})
        socket.receive_json()  # session_ready
        socket.send_bytes(_binary_frame(
            {"segmentId": "segment-1", "sequence": 4, "sampleStart": 0, "captureStartSample": 0,
             "primaryStartSample": 0, "sampleRate": 16_000}, b"\x00\x00" * 320))
        socket.receive_json()  # audio_buffered

    events = dict(logged)
    assert "stt_hybrid_websocket_failed" not in events, events.get("stt_hybrid_websocket_failed")
    assert events["stt_connection_opened"]["connection_id"]
    assert events["stt_session_ready"]["session_id"] == "stt-session-1"
    opened = events["stt_segment_opened"]
    assert (opened["segment_id"], opened["segment_sequence"], opened["session_id"]) == ("segment-1", 4, "stt-session-1")
    closed = events["stt_connection_closed"]
    assert closed["session_id"] == "stt-session-1"
    assert closed["segments_released"] == 1
    assert closed["close_code"] is not None


def test_a_record_keeps_counts_and_never_the_words(monkeypatch) -> None:
    written: list[str] = []
    monkeypatch.setattr(stt_stream_diagnostics._LOGGER, "info", written.append)

    stt_stream_diagnostics.stt_stream_log(
        "stt_hybrid_final_completed", segment_id="segment-1", transcript_chars=21,
        text="why did you not answer", transcript="why did you not answer",
    )

    record = json.loads(written[0])
    assert record["event"] == "stt_hybrid_final_completed"
    assert record["segment_id"] == "segment-1"
    assert record["transcript_chars"] == len("why did you not answer")
    assert "why did you" not in written[0]
    assert {"timestamp_utc", "sequence", "process_id"} <= set(record)
