"""Trial takes: test lines from a clip that is not a library voice, measured, and nothing of the clip kept."""
from __future__ import annotations

import base64
import contextlib
import io
import json
import secrets
import wave
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from services.tts import tts_trial_takes
from services.tts.tts_trial_takes import measure, parse_lines

RATE = 24_000


def _audio(*parts: tuple[float, float]) -> np.ndarray:
    return np.concatenate([np.full(int(seconds * RATE), level, dtype=np.float32) for seconds, level in parts])


def test_a_take_is_measured_for_its_voice_and_the_quiet_before_it() -> None:
    take = measure(_audio((0.32, 0.0), (1.2, 0.1), (0.4, 0.0)), RATE)

    assert take["seconds"] == pytest.approx(1.92, abs=0.01)
    assert take["voiced_seconds"] == pytest.approx(1.2, abs=0.09)
    assert take["lead_seconds"] == pytest.approx(0.32, abs=0.09)
    silent = measure(_audio((2.0, 0.001)), RATE)
    assert silent["voiced_seconds"] == 0.0 and silent["lead_seconds"] == pytest.approx(2.0, abs=0.09)


@pytest.mark.parametrize(("raw", "takes"), [
    ("[]", 2), ('["ok", ""]', 2), ('"not a list"', 2), (json.dumps(["x" * 201]), 2), ('["ok"]', 5),
    (json.dumps(["line"] * 33), 2),
])
def test_bad_test_lines_are_refused(raw: str, takes: int) -> None:
    with pytest.raises(ValueError):
        parse_lines(raw, takes)


def test_the_live_token_budget_is_used() -> None:
    assert tts_trial_takes.token_budget("Yeah, well,") == 36
    assert tts_trial_takes.token_budget("x" * 60) == round(41 + 45 * 1.167)


class _Provider:
    supports_reference_trials = True

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.forgotten: list[str] = []

    def generate_audio_stream(self, **kwargs: Any):
        self.calls.append(kwargs)
        # The clip exists while it is used, and it is the uploaded one.
        with open(kwargs["reference_audio"], "rb") as clip:
            assert clip.read() == b"RIFF-clip"
        voiced = 0.0 if len(self.calls) == 1 else 0.1
        yield _audio((0.08, 0.0), (0.9, voiced)), RATE, {}

    def forget_reference(self, path: str) -> int:
        self.forgotten.append(path)
        return 1


@contextlib.contextmanager
def _no_permit(*_args: Any, **_kwargs: Any):
    yield None


def _client(monkeypatch, provider: Any):
    from fastapi.testclient import TestClient

    from app.security.service_token import service_headers
    from services.tts import tts_server

    monkeypatch.setenv("OMNIX_SERVICE_TOKEN", secrets.token_urlsafe(32))
    monkeypatch.setenv("OMNIX_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")
    monkeypatch.setattr(tts_server, "_TTS_PROVIDER", provider)
    monkeypatch.setattr(tts_server, "_TTS_PROVIDER_ERROR", "")
    monkeypatch.setattr(tts_server, "device_permit_slot", _no_permit)
    return TestClient(tts_server.app, base_url="http://127.0.0.1", headers=service_headers())


def test_the_service_renders_each_line_and_drops_the_clip_afterwards(monkeypatch) -> None:
    provider = _Provider()
    client = _client(monkeypatch, provider)

    response = client.post(
        "/api/tts/trial_takes",
        files={"file": ("section.wav", b"RIFF-clip", "audio/wav")},
        data={"phrases": json.dumps(["Yeah, well,", "Look, I get it."]), "ref_text": "the section's words",
              "takes": "2"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True and len(body["takes"]) == 4
    assert body["takes"][0]["voiced_seconds"] == 0.0 and body["takes"][1]["voiced_seconds"] > 0.8
    assert [take["line"] for take in body["takes"]] == [0, 0, 1, 1]
    with wave.open(io.BytesIO(base64.b64decode(body["takes"][1]["audio_16k"]))) as audio:
        assert audio.getframerate() == 16_000
    # Live settings, the clip given directly, no library voice.
    assert all(call["reference_audio"] == provider.calls[0]["reference_audio"] for call in provider.calls)
    assert provider.calls[0]["ref_text"] == "the section's words" and provider.calls[0]["speaker"] is None
    assert provider.calls[0]["temperature"] == 0.6 and provider.calls[0]["chunk_size"] == 4
    # The route holds the permit; the engine must not wait for a second one (it timed out on 2026-11-07).
    assert all(call["_device_permit_held"] is True for call in provider.calls)
    assert provider.forgotten == [provider.calls[0]["reference_audio"]]


def test_an_engine_that_cannot_test_a_clip_says_so(monkeypatch) -> None:
    client = _client(monkeypatch, SimpleNamespace(supports_reference_trials=False))

    response = client.post(
        "/api/tts/trial_takes", files={"file": ("section.wav", b"RIFF-clip", "audio/wav")},
        data={"phrases": json.dumps(["Yeah, well,"])},
    )

    assert response.json() == {"ok": False, "code": "trial_unsupported", "engine": response.json()["engine"]}


def test_the_qwen_engine_generates_from_a_given_clip_and_forgets_it(monkeypatch) -> None:
    from app.providers import faster_qwen3_tts_provider as qwen

    seen: list[dict[str, Any]] = []

    class _Model:
        _voice_prompt_cache = {("C:/trial/reference.wav", "words", False, False, ()): "prompt",
                               ("C:/voices/Jinx.wav", "", True, False, ()): "kept"}

        def generate_voice_clone_streaming(self, **kwargs: Any):
            seen.append(kwargs)
            yield np.zeros(240, dtype=np.float32), RATE, {}

    model = _Model()
    provider = qwen.FasterQwen3TTSProvider({})
    monkeypatch.setattr(provider, "_get_model", lambda: model)
    monkeypatch.setattr(qwen, "_clone_reference", lambda _speaker: pytest.fail("a trial looked up a library voice"))
    monkeypatch.setattr(qwen._model_loader, "model", model, raising=False)

    list(provider.generate_audio_stream("Yeah, well,", speaker=None, reference_audio="C:/trial/reference.wav",
                                        ref_text="words"))

    assert seen[0]["ref_audio"] == "C:/trial/reference.wav" and seen[0]["ref_text"] == "words"
    assert provider.forget_reference("C:/trial/reference.wav") == 1
    assert list(model._voice_prompt_cache) == [("C:/voices/Jinx.wav", "", True, False, ())]
