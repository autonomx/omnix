from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import tts_server
from app import tts_http_client
from app.voice_debug import text_fingerprint, voice_debug_log, voice_debug_log_path


def test_voice_debug_log_writes_json_without_speech_content(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_VOICE_DEBUG_LOG_DIR", str(tmp_path))
    channel = f"test-{uuid.uuid4()}"
    secret_text = "This sentence must not be written into the debug log."

    voice_debug_log(
        channel,
        "test_event",
        trace_id="trace:test",
        speaker="Jinx",
        text_chars=len(secret_text),
        text_fingerprint=text_fingerprint(secret_text),
    )

    log_path = Path(voice_debug_log_path(channel))
    record = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert record["event"] == "test_event"
    assert record["speaker"] == "Jinx"
    assert record["text_chars"] == len(secret_text)
    assert record["text_fingerprint"] == text_fingerprint(secret_text)
    assert secret_text not in log_path.read_text(encoding="utf-8")


def test_voice_debug_logger_cache_is_bounded_expiring_and_clearable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import app.voice_debug as voice_debug

    voice_debug.clear_voice_debug_loggers()
    monkeypatch.setenv("OMNIX_VOICE_DEBUG_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(voice_debug, "MAX_VOICE_DEBUG_LOGGERS", 1)
    monkeypatch.setattr(voice_debug, "VOICE_DEBUG_LOGGER_TTL_SECONDS", 5.0)
    now = {"value": 10.0}
    monkeypatch.setattr(voice_debug.time, "monotonic", lambda: now["value"])

    first = voice_debug._logger("first")
    first_handler = first.handlers[0]
    first.info("first")
    assert first_handler.stream is not None
    second = voice_debug._logger("second")
    assert first_handler.stream is None
    assert list(voice_debug._LOGGERS) == ["second"]

    now["value"] = 16.0
    second_handler = second.handlers[0]
    second.info("second")
    assert second_handler.stream is not None
    voice_debug._logger("second")
    assert second_handler.stream is None
    voice_debug.clear_voice_debug_loggers()
    assert not voice_debug._LOGGERS


def test_tts_reference_snapshot_exposes_exact_and_fallback_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tts_server, "VOICE_CLONES_DIR", str(tmp_path))
    (tmp_path / "Jinx.wav").write_bytes(b"jinx")
    (tmp_path / "default_ref.wav").write_bytes(b"default")

    exact = tts_server._voice_reference_snapshot("Jinx")
    assert exact["resolution_strategy"] == "exact_speaker"
    assert exact["requested_path_exists"] is True
    assert exact["resolved_reference_name"] == "Jinx.wav"

    fallback = tts_server._voice_reference_snapshot("Inigo")
    assert fallback["resolution_strategy"] == "default_ref_fallback"
    assert fallback["requested_path_exists"] is False
    assert fallback["resolved_reference_name"] == "default_ref.wav"
    assert fallback["available_wav_files"] == ["default_ref.wav", "Jinx.wav"]


def test_backend_stream_forward_includes_speaker_and_trace_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_VOICE_DEBUG_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("OMNIX_SERVICE_TOKEN", "t" * 43)
    captured: dict[str, Any] = {}

    class FakeResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.headers = {"content-type": "application/json"}
            self.content = b'{"success": false, "error": "debug-only"}'

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict[str, Any]:
            return {"success": False, "error": "debug-only"}

    def fake_post(
        url: str,
        *,
        json: dict[str, Any],
        timeout: float,
        headers: dict[str, str] | None = None,
        allow_redirects: bool = True,
    ) -> FakeResponse:
        captured.update({
            "url": url,
            "json": json,
            "timeout": timeout,
            "headers": headers,
            "allow_redirects": allow_redirects,
        })
        return FakeResponse()

    monkeypatch.setattr(tts_http_client.requests, "post", fake_post)
    result = tts_http_client.tts_generate_stream_audio(text="hello", speaker="Inigo")

    assert result == {"success": False, "error": "debug-only"}
    assert captured["json"]["speaker"] == "Inigo"
    assert captured["json"]["trace_id"].startswith("tts-stream:")
    assert captured["json"]["text"] == "hello"
    assert captured["headers"]
    assert captured["allow_redirects"] is False
