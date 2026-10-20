"""The TTS provider contract every local engine keeps (Voice Studio Phase 5).

A provider declares only what it does: a catalogued capability matches the
provider object's own answer, it can start and stop, and its sliders map to
real generation parameters. OmniVoice's synthesis and cloning are exercised
against a fake child server.
"""
from __future__ import annotations

import base64
import io
import json
import wave
from typing import Any

import httpx
import pytest

from app.platform.voice.output_settings import engine_controls, sampling_overrides
from app.providers.catalog import LOCAL_DEVICE, STREAMING, VOICE_CLONE, specs

LOCAL_ENGINES = [spec for spec in specs("tts") if LOCAL_DEVICE in spec.capabilities]


@pytest.mark.parametrize("spec", LOCAL_ENGINES, ids=lambda spec: spec.id)
def test_a_local_engine_declares_only_what_it_does(spec) -> None:
    provider = spec.load()({})
    assert provider.provider_name == spec.id
    for method in ("start", "stop", "generate_audio", "get_speakers", "resolve_generation_parameters"):
        assert callable(getattr(provider, method, None)), method
    assert provider.supports_voice_cloning() == (VOICE_CLONE in spec.capabilities)
    assert provider.supports_streaming() == (STREAMING in spec.capabilities)


@pytest.mark.parametrize("spec", LOCAL_ENGINES, ids=lambda spec: spec.id)
def test_every_engine_slider_reaches_a_generation_parameter(spec) -> None:
    provider = spec.load()({})
    for control in engine_controls(spec.id):
        if control in {"speed", "pitch", "volume"}:
            continue  # applied to the audio, the same way for every engine
        overrides = sampling_overrides(spec.id, {control: 0.2})
        assert overrides, f"{spec.id}: the {control} slider changes nothing"
        resolved = provider.resolve_generation_parameters(overrides)
        for key, value in overrides.items():
            assert resolved.get(key) == value, f"{spec.id}: {key} is not a parameter the engine reads"


# --- OmniVoice against a fake child server ----------------------------------------------------


def _wav(seconds: float = 0.5, rate: int = 24_000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(rate)
        target.writeframes(b"\x00\x00" * int(rate * seconds))
    return buffer.getvalue()


@pytest.fixture
def omnivoice(monkeypatch, tmp_path):
    from contextlib import nullcontext

    from app.providers import omnivoice_provider as module

    sample = tmp_path / "jinx.wav"
    sample.write_bytes(_wav(3.0))
    monkeypatch.setattr(module, "clone_reference",
                        lambda speaker: (str(sample), "I am Jinx.") if speaker == "voice-cloning:jinx" else (None, ""))
    monkeypatch.setattr(module, "generation_slot", nullcontext)
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-omnix-child-token"] == provider.server.token
        seen.append(json.loads(request.content))
        return httpx.Response(200, content=_wav(1.0), headers={"content-type": "audio/wav"})

    provider = module.OmniVoiceTTSProvider({"num_step": 16})
    provider.server._http_client = httpx.Client(transport=httpx.MockTransport(handler),
                                                headers={"X-Omnix-Child-Token": provider.server.token})
    return provider, seen


def test_omnivoice_synthesises_with_its_automatic_voice_without_a_sample(omnivoice) -> None:
    provider, seen = omnivoice
    result = provider.generate_audio("Bonjour tout le monde.", speaker="default", language="fr")
    assert result["success"] and result["sample_rate"] == 24_000 and result["duration"] == pytest.approx(1.0)
    assert seen == [{"text": "Bonjour tout le monde.", "num_step": 16, "language": "fr"}]


def test_omnivoice_clones_a_library_voice_from_its_sample_and_words(omnivoice) -> None:
    provider, seen = omnivoice
    result = provider.generate_audio("Hello.", speaker="voice-cloning:jinx", seed=7, speed=1.2,
                                     instruct="angrily")
    assert result["success"]
    request = seen[0]
    assert request["ref_text"] == "I am Jinx." and base64.b64decode(request["ref_audio"])[:4] == b"RIFF"
    assert request["seed"] == 7 and request["speed"] == 1.2
    assert "instruct" not in request  # a delivery note is not a speaker attribute


def test_omnivoice_reports_a_server_failure_as_a_failed_synthesis(monkeypatch, omnivoice) -> None:
    provider, _seen = omnivoice
    provider.server._http_client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503)))
    result = provider.generate_audio("Hello.")
    assert result["success"] is False and "503" in result["error"]


def test_omnivoice_will_not_start_without_its_weights(monkeypatch, tmp_path) -> None:
    from app.providers import omnivoice_provider as module

    provider = module.OmniVoiceTTSProvider({"model_dir": str(tmp_path / "missing")})
    monkeypatch.setattr("app.settings.access.load_settings",
                        lambda: {"omnivoice": {"model_dir": str(tmp_path / "missing")}})
    monkeypatch.setattr(provider.server, "launch_and_wait", lambda: pytest.fail("must not launch without weights"))
    state = provider.start()
    assert state["running"] is False and "weights are missing" in state["error"]
    with pytest.raises(Exception, match="Models tool"):
        module.OmniVoiceTTSProvider.local_model_artifacts()


def test_the_child_server_command_uses_the_omnivoice_environment(monkeypatch, tmp_path) -> None:
    from app.providers import omnivoice_provider as module

    provider = module.OmniVoiceTTSProvider({"python": "C:/envs/omnix-omnivoice/python.exe",
                                            "model_dir": str(tmp_path), "port": 5199})
    command = provider._server_command()
    assert command[0] == "C:/envs/omnix-omnivoice/python.exe"
    assert command[1].endswith("omnivoice_server.py")
    assert command[command.index("--port") + 1] == "5199"
