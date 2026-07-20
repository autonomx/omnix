from __future__ import annotations

import importlib.util
import io
import json
import sys
import wave
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "generate_live_voice_cue_pack.py"


def load_generator_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_live_voice_cue_pack_test_target", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


GENERATOR = load_generator_module()


class FakeResponse:
    def __init__(self, payload: bytes, *, content_type: str = "application/json") -> None:
        self._payload = payload
        self.headers = {"Content-Type": content_type}

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def wav_payload(*, sample_rate: int = 24_000, frames: int = 240) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * frames)
    return buffer.getvalue()


def test_synthesize_via_server_posts_request_and_validates_wav(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    expected_wav = wav_payload(sample_rate=24_000, frames=321)

    def fake_urlopen(request: Any, *, timeout: float) -> FakeResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse(expected_wav, content_type="audio/wav")

    monkeypatch.setattr(GENERATOR.urllib.request, "urlopen", fake_urlopen)

    wav_bytes, sample_rate, sample_count = GENERATOR.synthesize_via_server(
        "http://127.0.0.1:5101/",
        voice_id="Jinx",
        text="Mhm.",
        language="English",
        variant=2,
        timeout=12.0,
    )

    request = captured["request"]
    assert request.full_url == "http://127.0.0.1:5101/api/tts/generate_stream_audio"
    assert request.get_method() == "POST"
    assert captured["timeout"] == 12.0
    assert json.loads(request.data.decode("utf-8")) == {
        "text": "Mhm.",
        "speaker": "Jinx",
        "language": "English",
        "chunk_size": 8,
        "temperature": 0.64,
        "top_k": 20,
        "top_p": 0.85,
        "repetition_penalty": 1.05,
        "append_silence": False,
        "max_new_tokens": 64,
    }
    assert wav_bytes == expected_wav
    assert sample_rate == 24_000
    assert sample_count == 321


def test_require_ready_tts_server_rejects_not_ready_service(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps({"ok": False, "status": "not_ready", "error": "model unavailable"}).encode("utf-8")

    def fake_urlopen(_url: str, *, timeout: float) -> FakeResponse:
        assert timeout == 5.0
        return FakeResponse(payload)

    monkeypatch.setattr(GENERATOR.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(SystemExit, match="model unavailable"):
        GENERATOR.require_ready_tts_server("http://127.0.0.1:5101", timeout=5.0)


def test_inspect_wav_rejects_empty_audio() -> None:
    empty = wav_payload(frames=0)
    with pytest.raises(RuntimeError, match="unsupported WAV"):
        GENERATOR.inspect_wav(empty)
