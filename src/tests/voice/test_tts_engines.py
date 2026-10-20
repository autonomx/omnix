from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.platform.voice import tts_engines


@pytest.fixture(autouse=True)
def idle_switch():
    tts_engines._update(provider=None, phase="idle", error=None,
                        voices={"prepared": [], "failed": [], "already_ready": 0})
    yield
    tts_engines._update(provider=None, phase="idle", error=None,
                        voices={"prepared": [], "failed": [], "already_ready": 0})


class FakeStt:
    provider_name = "parakeet"

    def __init__(self, failing: set[str] = frozenset()):
        self.failing = failing
        self.calls: list[str] = []

    def transcribe(self, path, language=None):
        self.calls.append(path)
        if any(path.endswith(name) for name in self.failing):
            return {"success": False, "error": "no speech detected"}
        return {"success": True, "text": f"words of {path.rsplit(chr(92), 1)[-1].rsplit('/', 1)[-1]}"}


def test_samples_without_a_transcript_are_transcribed_once(tmp_path, monkeypatch):
    ready = tmp_path / "Ehsan.mp3"
    ready.write_bytes(b"a")
    (tmp_path / "Ehsan.json").write_text(json.dumps({"ref_text": "Kept as written.", "language": "English"}), encoding="utf-8")
    missing = tmp_path / "Donald Trump.wav"
    missing.write_bytes(b"b")
    no_text = tmp_path / "Maya.wav"
    no_text.write_bytes(b"c")
    (tmp_path / "Maya.json").write_text(json.dumps({"voice_id": "Maya", "speaker": "default"}), encoding="utf-8")
    silent = tmp_path / "default_ref.wav"
    silent.write_bytes(b"d")
    monkeypatch.setattr(tts_engines, "_voice_samples", lambda: [
        ("voice-cloning:Ehsan", ready, "English"), ("voice-cloning:Donald-Trump", missing, ""),
        ("voice-cloning:Maya", no_text, "en"), ("voice-cloning:default_ref", silent, ""),
    ])
    stt = FakeStt(failing={"default_ref.wav"})
    monkeypatch.setattr("app.providers.service.get_stt_provider", lambda name=None: stt)

    result = tts_engines.prepare_voice_transcripts()

    assert result == {
        "prepared": ["voice-cloning:Donald-Trump", "voice-cloning:Maya"],
        "failed": [{"voice_id": "voice-cloning:default_ref", "error": "STT returned no transcript: no speech detected"}],
        "already_ready": 1,
    }
    assert json.loads((tmp_path / "Ehsan.json").read_text(encoding="utf-8"))["ref_text"] == "Kept as written."
    trump = json.loads((tmp_path / "Donald Trump.json").read_text(encoding="utf-8"))
    assert trump["ref_text"] == "words of Donald Trump.wav"
    assert trump["transcript_source"] == "stt"
    maya = json.loads((tmp_path / "Maya.json").read_text(encoding="utf-8"))
    assert maya["speaker"] == "default"  # Existing sidecar fields survive.
    assert maya["ref_text"] == "words of Maya.wav"
    assert not (tmp_path / "default_ref.json").exists()

    assert tts_engines.prepare_voice_transcripts()["prepared"] == []  # Nothing left to do.


def test_only_local_engines_can_be_selected():
    with pytest.raises(ValueError):
        tts_engines.select_tts_engine("parakeet")


def test_selecting_an_engine_saves_the_default_then_unloads_prepares_and_loads(monkeypatch):
    events: list[tuple] = []
    settings = {"audio_provider_tts": "faster-qwen3-tts"}
    monkeypatch.setattr("app.settings.access.load_settings", lambda: dict(settings))
    monkeypatch.setattr("app.settings.access.save_settings", lambda values: (settings.update(values), events.append(("save", values))))
    monkeypatch.setattr("app.providers.service.invalidate_audio_provider_cache", lambda kind=None: events.append(("unload", kind)))
    monkeypatch.setattr(tts_engines, "prepare_voice_transcripts", lambda: (events.append(("prepare",)), {
        "prepared": ["voice-cloning:Jinx"], "failed": [], "already_ready": 4})[1])
    monkeypatch.setattr("app.platform.voice.tts_runtime_actions.warm_tts_runtime",
                        lambda trigger: (events.append(("load", trigger)), {"status": "ready"})[1])
    monkeypatch.setattr(tts_engines.threading, "Thread",
                        lambda target, args, **_: SimpleNamespace(start=lambda: target(*args)))
    monkeypatch.setattr(tts_engines, "tts_engines", lambda: tts_engines._snapshot())

    state = tts_engines.select_tts_engine("fish-s2-pro")

    assert events == [("save", {"audio_provider_tts": "fish-s2-pro"}), ("unload", "tts"), ("prepare",),
                      ("load", "engine-switch")]
    assert state["phase"] == "ready"
    assert state["voices"]["prepared"] == ["voice-cloning:Jinx"]


def test_a_failed_load_is_reported(monkeypatch):
    monkeypatch.setattr("app.settings.access.load_settings", lambda: {"audio_provider_tts": "faster-qwen3-tts"})
    monkeypatch.setattr("app.providers.service.invalidate_audio_provider_cache", lambda kind=None: None)
    monkeypatch.setattr("app.platform.voice.tts_runtime_actions.warm_tts_runtime",
                        lambda trigger: {"status": "failed", "error": "CUDA out of memory"})
    monkeypatch.setattr(tts_engines.threading, "Thread",
                        lambda target, args, **_: SimpleNamespace(start=lambda: target(*args)))
    monkeypatch.setattr(tts_engines, "tts_engines", lambda: tts_engines._snapshot())

    state = tts_engines.select_tts_engine("faster-qwen3-tts")

    assert state["phase"] == "failed"
    assert state["error"] == "CUDA out of memory"


def test_a_second_switch_waits_for_the_first():
    tts_engines._update(provider="fish-s2-pro", phase="loading")

    with pytest.raises(RuntimeError, match="still in progress"):
        tts_engines.select_tts_engine("faster-qwen3-tts")


def test_the_engine_list_marks_the_selected_engine_and_its_install_state(monkeypatch):
    monkeypatch.setattr("app.providers.service.load_settings", lambda: {"audio_provider_tts": "fish-s2-pro"})
    monkeypatch.setattr(tts_engines, "_installed", lambda provider_id: (provider_id == "faster-qwen3-tts", "missing weights"))

    listing = tts_engines.tts_engines()

    assert listing["selected"] == "fish-s2-pro"
    by_id = {engine["id"]: engine for engine in listing["engines"]}
    # The voice-design engine is a tool, never listed for selection.
    assert set(by_id) == {"faster-qwen3-tts", "fish-s2-pro", "omnivoice"}
    assert by_id["omnivoice"]["needs_transcripts"] is True
    assert by_id["fish-s2-pro"]["selected"] is True
    assert by_id["fish-s2-pro"]["installed"] is False
    assert by_id["fish-s2-pro"]["needs_transcripts"] is True
    assert by_id["faster-qwen3-tts"]["needs_transcripts"] is False
    assert "similarity" not in by_id["fish-s2-pro"]["voice_controls"]
    assert "similarity" in by_id["faster-qwen3-tts"]["voice_controls"]
    assert listing["switch"]["phase"] == "idle"
