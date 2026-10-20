"""Voice Studio Phase 3: voice design.

The VoiceDesign engine is faked here (its real-model check is in the roadmap);
these tests pin what the platform owns: the engine is never selectable, design
jobs pin it so the swap controller loads it, candidates and saved voices are
stored with their description and seed, and a saved voice carries its
transcript.
"""
from __future__ import annotations

import base64
import io
import wave
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from app.assets.models import AssetRecord, AssetType
from app.jobs.models import JobRecord
from app.platform.voice import design, jobs as voice_jobs

RATE = 24_000


def _speech_wav(seconds: float = 2.0, frequency: float = 180.0) -> bytes:
    """A voiced, speech-like tone with pauses, so sample cleanup has something to keep."""
    time = np.arange(int(RATE * seconds)) / RATE
    signal = 0.3 * np.sin(2 * np.pi * frequency * time) * (0.6 + 0.4 * np.sin(2 * np.pi * 3 * time))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(RATE)
        target.writeframes((signal * 32767).astype("<i2").tobytes())
    return buffer.getvalue()


class _AssetStore:
    def __init__(self) -> None:
        self.assets: dict[str, AssetRecord] = {}

    def get_asset(self, asset_id: str) -> AssetRecord | None:
        return self.assets.get(asset_id)

    def upsert_asset(self, asset: AssetRecord) -> AssetRecord:
        self.assets[asset.id] = asset
        return asset


class _JobStore:
    def __init__(self) -> None:
        self.completed: dict[str, Any] = {}
        self.failed: dict[str, Any] = {}
        self.deferred: list[tuple[str, str]] = []

    def mark_running(self, job_id: str) -> None:
        pass

    def complete_job(self, job_id: str, request: Any) -> None:
        self.completed[job_id] = request

    def fail_job(self, job_id: str, request: Any) -> None:
        self.failed[job_id] = request

    def defer_job(self, job_id: str, *, delay_seconds: float, reason: str) -> None:
        self.deferred.append((job_id, reason))


class _DesignEngine:
    provider_name = design.DESIGN_ENGINE

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def generate_audio(self, text: str, language: str | None = None, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"text": text, "language": language, **kwargs})
        seconds = 17.0 if len(text) > 150 else 2.0
        return {"success": True, "audio_base64": base64.b64encode(_speech_wav(seconds)).decode("ascii"),
                "duration": seconds}


def _job(job_type: str, payload: dict[str, Any]) -> JobRecord:
    return JobRecord.model_validate({
        "id": f"job-{job_type.replace('.', '-')}", "module": "voice", "type": job_type, "status": "running",
        "resource_class": "gpu:tts", "input_payload": payload,
        "created_at": "2026-10-19T00:00:00+00:00", "updated_at": "2026-10-19T00:00:00+00:00",
    })


@pytest.fixture
def stores(tmp_path: Path, monkeypatch) -> _AssetStore:
    import app.assets as assets_module

    store = _AssetStore()
    monkeypatch.setattr(assets_module, "default_asset_store", lambda: store)
    monkeypatch.setattr(voice_jobs, "default_asset_store", lambda: store)
    monkeypatch.setattr(voice_jobs, "resources_data_root", lambda: tmp_path)
    monkeypatch.setattr("app.runtime.paths.resources_data_root", lambda: tmp_path)
    monkeypatch.setattr(voice_jobs, "_voice_clone_dir", lambda: tmp_path / "voice_clones")
    monkeypatch.setattr(voice_jobs, "_upsert_legacy_voice_manifest", lambda *args, **kwargs: None)
    return store


@pytest.fixture
def engine(monkeypatch) -> _DesignEngine:
    fake = _DesignEngine()
    monkeypatch.setattr(design, "_design_engine", lambda: fake)
    return fake


# --- The engine is a voice tool, never the selected engine ------------------------------------


def test_the_design_engine_is_never_listed_or_selectable(monkeypatch) -> None:
    from app.platform.voice import tts_engines
    from app.providers.service import selected_tts_provider_id

    assert design.DESIGN_ENGINE not in tts_engines.local_engine_ids()
    assert "faster-qwen3-tts" in tts_engines.local_engine_ids()
    with pytest.raises(ValueError, match="voice design tool"):
        tts_engines.select_tts_engine(design.DESIGN_ENGINE)
    # A setting naming it (written by hand, or by an older client) falls back to the default.
    assert selected_tts_provider_id({"audio_provider_tts": design.DESIGN_ENGINE}) == "faster-qwen3-tts"
    assert selected_tts_provider_id({"audio_provider_tts": "fish-s2-pro"}) == "fish-s2-pro"


def test_the_design_provider_loads_its_own_checkpoint_whatever_the_service_env_says(monkeypatch, tmp_path: Path) -> None:
    from app.providers import qwen3_voice_design_provider as module

    monkeypatch.setenv("OMNIX_TTS_MODEL_DIR", str(tmp_path / "Qwen3-TTS-12Hz-0.6B-Base"))
    monkeypatch.setattr(module, "voice_design_model_dir", lambda: tmp_path / "VoiceDesign")
    provider = module.Qwen3VoiceDesignProvider({})
    assert provider._model_config["model_name"] == str(tmp_path / "VoiceDesign")
    assert not provider.supports_voice_cloning() and not provider.supports_streaming()


def test_the_design_provider_needs_a_description_and_passes_the_seed(monkeypatch) -> None:
    from contextlib import nullcontext

    from app.providers import qwen3_voice_design_provider as module

    seen: dict[str, Any] = {}

    class _Model:
        def generate_voice_design(self, **kwargs: Any) -> tuple[list[np.ndarray], int]:
            seen.update(kwargs)
            return [np.full(24_000, 0.5, dtype=np.float32)], 24_000

    seeds: list[int | None] = []
    monkeypatch.setattr(module, "generation_slot", nullcontext)
    monkeypatch.setattr(module, "seeded", seeds.append)
    provider = module.Qwen3VoiceDesignProvider({})
    monkeypatch.setattr(provider, "_get_model", lambda: _Model())
    assert provider.generate_audio("Hello", language="de")["success"] is False  # no description
    result = provider.generate_audio("Hello", language="de", instruct="a warm baritone", seed=42, temperature=0.7)
    assert result["success"] and result["duration"] == pytest.approx(1.0)
    assert seeds == [42]
    assert seen["instruct"] == "a warm baritone" and seen["language"] == "German" and seen["temperature"] == 0.7
    with wave.open(io.BytesIO(base64.b64decode(result["audio_base64"]))) as clip:
        assert clip.getframerate() == 24_000


# --- Design jobs ------------------------------------------------------------------------------


def test_generate_renders_one_candidate_per_seed_on_the_design_engine(stores, engine) -> None:
    store = _JobStore()
    job = _job("voice.design", {"description": "a calm woman in her sixties, slight Irish accent",
                                "preview_text": "Good evening.", "language": "en", "seeds": [11, 22, 33]})
    voice_jobs.execute_voice_studio_job(store, job)
    assert job.id in store.completed, store.failed.get(job.id)
    assert [call["seed"] for call in engine.calls] == [11, 22, 33]
    assert all(call["instruct"].startswith("a calm woman") and call["text"] == "Good evening." for call in engine.calls)
    refs = store.completed[job.id].output_refs
    assert [ref["seed"] for ref in refs] == [11, 22, 33]
    assert all(ref["audio_url"] == f"/api/assets/{ref['asset_id']}/audio" for ref in refs)
    candidate = stores.assets[refs[0]["asset_id"]]
    assert candidate.metadata["kind"] == "voice_design_candidate" and candidate.metadata["seed"] == 11


def test_without_seeds_three_random_candidates_are_made(stores, engine) -> None:
    store = _JobStore()
    voice_jobs.execute_voice_studio_job(store, _job("voice.design", {"description": "a robot butler"}))
    seeds = [call["seed"] for call in engine.calls]
    assert len(seeds) == 3 and len(set(seeds)) == 3
    assert engine.calls[0]["text"] == design.REFERENCE_PASSAGES["en"]   # the passage a saved voice clones from


@pytest.mark.parametrize("payload", [
    {"description": ""},
    {"description": "x" * 601},
    {"description": "a voice", "seeds": [1, 2, 3, 4]},
    {"description": "a voice", "seeds": ["soon"]},
])
def test_bad_design_requests_fail_without_retry(stores, engine, payload: dict[str, Any]) -> None:
    store = _JobStore()
    job = _job("voice.design", payload)
    voice_jobs.execute_voice_studio_job(store, job)
    assert store.failed[job.id].code == "invalid_request" and store.failed[job.id].retryable is False
    assert engine.calls == []


def test_design_waits_for_the_swap_controller_to_load_the_engine(monkeypatch, stores) -> None:
    from app.providers.exceptions import TtsEngineNotLoaded

    requested: list[tuple[str, str]] = []

    def not_loaded() -> Any:
        raise TtsEngineNotLoaded(design.DESIGN_ENGINE, loaded="faster-qwen3-tts")

    monkeypatch.setattr(design, "_design_engine", not_loaded)
    monkeypatch.setattr("app.platform.voice.swap_controller.swaps_enabled", lambda: True)
    monkeypatch.setattr("app.persistence.tts_swap.swap_request_failure", lambda job_id: None)
    monkeypatch.setattr("app.persistence.tts_swap.swap_wait_seconds", lambda job_id: 0.0)
    monkeypatch.setattr("app.persistence.tts_swap.request_swap", lambda engine, job_id: requested.append((engine, job_id)))
    store = _JobStore()
    job = _job("voice.design", {"description": "a gravelly pirate"})
    voice_jobs.execute_voice_studio_job(store, job)
    assert requested == [(design.DESIGN_ENGINE, job.id)]
    assert store.deferred and not store.failed and not store.completed


def test_design_needs_the_tts_service(monkeypatch, stores) -> None:
    monkeypatch.setattr("app.platform.voice.swap_controller.swaps_enabled", lambda: False)
    store = _JobStore()
    job = _job("voice.design", {"description": "a gravelly pirate"})
    voice_jobs.execute_voice_studio_job(store, job)
    assert "TTS service" in store.failed[job.id].message


def test_save_renders_the_reference_passage_and_stores_a_designed_voice(stores, engine, monkeypatch) -> None:
    monkeypatch.setattr("app.providers.qwen3_voice_design_provider.design_model_revision", lambda: "abc123")
    store = _JobStore()
    job = _job("voice.design.save", {"description": "a warm baritone narrator", "seed": 22, "language": "en",
                                     "profile_name": "Narrator Bob"})
    voice_jobs.execute_voice_studio_job(store, job)
    assert job.id in store.completed, store.failed.get(job.id)
    assert engine.calls[0]["text"] == design.REFERENCE_PASSAGES["en"] and engine.calls[0]["seed"] == 22
    voice = next(asset for asset in stores.assets.values() if asset.type == AssetType.VOICE_PROFILE)
    assert voice.metadata["source"] == "designed"
    assert voice.metadata["reference_text"] == design.REFERENCE_PASSAGES["en"]
    assert voice.metadata["design"] == {
        "description": "a warm baritone narrator", "seed": 22, "language": "en", "engine": design.DESIGN_ENGINE,
        "model_revision": "abc123", "parameters": {"temperature": 0.9, "top_k": 50, "top_p": 1.0,
                                                   "repetition_penalty": 1.05},
        "reference_seconds": 17.0,
    }
    # The transcript sits beside the sample, so Fish S2 Pro clones it without STT.
    from app.assets.voice_clone_identity import reference_transcript

    assert reference_transcript(Path(voice.storage_path)) == design.REFERENCE_PASSAGES["en"]


def test_save_keeps_the_candidate_the_person_heard(stores, engine) -> None:
    """The chosen candidate's own audio and words become the voice: no new render, no different voice."""
    store = _JobStore()
    designed = _job("voice.design", {"description": "a warm baritone narrator", "preview_text": "Hello there, friend.",
                                     "seeds": [5]})
    voice_jobs.execute_voice_studio_job(store, designed)
    candidate = store.completed[designed.id].output_refs[0]["asset_id"]
    rendered = len(engine.calls)
    # The form has moved on (another language, no seed): the voice still records the candidate's.
    job = _job("voice.design.save", {"description": "a warm baritone narrator", "language": "de",
                                     "profile_name": "Narrator Bob", "candidate_asset_id": candidate})
    voice_jobs.execute_voice_studio_job(store, job)
    assert job.id in store.completed, store.failed.get(job.id)
    assert len(engine.calls) == rendered   # nothing rendered again
    voice = next(asset for asset in stores.assets.values() if asset.type == AssetType.VOICE_PROFILE)
    assert voice.metadata["reference_text"] == "Hello there, friend."
    assert voice.metadata["design"]["seed"] == 5 and voice.metadata["design"]["language"] == "en"
    other = _job("voice.design.save", {"description": "x", "seed": 5, "language": "en", "profile_name": "Nope",
                                       "candidate_asset_id": voice.id})
    voice_jobs.execute_voice_studio_job(store, other)
    assert "design candidates" in store.failed[other.id].message   # only a design candidate can be saved


def test_save_needs_a_name_and_a_language_with_a_passage(stores, engine) -> None:
    store = _JobStore()
    job = _job("voice.design.save", {"description": "a voice", "seed": 1, "language": "en"})
    voice_jobs.execute_voice_studio_job(store, job)
    assert store.failed[job.id].code == "invalid_request"
    job = _job("voice.design.save", {"description": "a voice", "seed": 1, "language": "ja", "profile_name": "Aiko"})
    voice_jobs.execute_voice_studio_job(store, job)
    assert "No reference passage" in store.failed[job.id].message


def test_every_reference_passage_lasts_about_15_to_20_seconds() -> None:
    # Speech runs at about 2.5-3 words a second.
    for language, passage in design.REFERENCE_PASSAGES.items():
        words = len(passage.split())
        assert 42 <= words <= 60, (language, words)


def test_design_jobs_are_registered_with_the_voice_feature() -> None:
    from app.platform.voice.feature import FEATURE

    types = {spec.type for spec in FEATURE.job_handlers}
    assert {"voice.design", "voice.design.save"} <= types
    assert {"voice.design", "voice.design.save"} <= voice_jobs.VOICE_STUDIO_JOB_TYPES


def test_candidates_read_the_reference_passage_without_a_sentence_of_their_own(stores, engine) -> None:
    store = _JobStore()
    job = _job("voice.design", {"description": "a calm narrator", "language": "de", "seeds": [3]})
    voice_jobs.execute_voice_studio_job(store, job)
    assert job.id in store.completed, store.failed.get(job.id)
    assert engine.calls[0]["text"] == design.REFERENCE_PASSAGES["de"]


# --- Blend (§5) ---------------------------------------------------------------------------------------


def test_speaker_embeddings_mix_by_weight() -> None:
    import numpy as np

    from app.providers.speaker_blend import mix_speaker_embeddings

    mixed = mix_speaker_embeddings([np.array([1.0, 0.0]), np.array([0.0, 1.0])], [3, 1])
    assert mixed.tolist() == [0.75, 0.25]
    with pytest.raises(ValueError):
        mix_speaker_embeddings([np.array([1.0])], [0])


def test_only_the_engine_with_embeddings_blends() -> None:
    from app.providers.catalog import VOICE_BLEND, provider_supports

    assert design.blend_engine_id() == "faster-qwen3-tts"
    assert provider_supports("faster-qwen3-tts", VOICE_BLEND, "tts")
    assert not provider_supports("fish-s2-pro", VOICE_BLEND, "tts")


def test_blend_saves_a_voice_between_two_library_voices(stores, monkeypatch) -> None:
    fake = _DesignEngine()
    pinned: list[str] = []
    monkeypatch.setattr("app.providers.service.pinned_tts_provider", lambda engine: pinned.append(engine) or fake)
    store = _JobStore()
    job = _job("voice.blend", {"voices": [{"voice": "voice-cloning:Anaka", "weight": 0.7},
                                          {"voice": "voice-cloning:Morgan", "weight": 0.3}],
                               "profile_name": "Anaka x Morgan", "language": "en"})
    voice_jobs.execute_voice_studio_job(store, job)
    assert job.id in store.completed, store.failed.get(job.id)
    assert pinned == ["faster-qwen3-tts"]
    assert fake.calls[0]["text"] == design.REFERENCE_PASSAGES["en"]
    assert fake.calls[0]["speaker_blend"] == [{"speaker": "voice-cloning:Anaka", "weight": 0.7},
                                              {"speaker": "voice-cloning:Morgan", "weight": 0.3}]
    voice = next(asset for asset in stores.assets.values() if asset.type == AssetType.VOICE_PROFILE)
    assert voice.metadata["source"] == "blended" and voice.metadata["reference_text"] == design.REFERENCE_PASSAGES["en"]
    assert voice.metadata["blend"]["engine"] == "faster-qwen3-tts"


@pytest.mark.parametrize(("voices", "message"), [
    ([{"voice": "voice-cloning:A", "weight": 0.5}], "two to four"),
    ([{"voice": "voice-cloning:A", "weight": 0.5}, {"voice": "voice-cloning:A", "weight": 0.5}], "different voices"),
    ([{"voice": "voice-cloning:A", "weight": 0.5}, {"voice": "C:/secret.wav", "weight": 0.5}], "library voice"),
    ([{"voice": "voice-cloning:A", "weight": 0}, {"voice": "voice-cloning:B", "weight": 1}], "weight above 0"),
])
def test_a_blend_names_two_to_four_different_library_voices(stores, monkeypatch, voices, message) -> None:
    monkeypatch.setattr("app.providers.service.pinned_tts_provider", lambda engine: _DesignEngine())
    store = _JobStore()
    job = _job("voice.blend", {"voices": voices, "profile_name": "X", "language": "en"})
    voice_jobs.execute_voice_studio_job(store, job)
    assert store.failed[job.id].code == "invalid_request" and message in store.failed[job.id].message


def test_the_tts_service_refuses_a_blend_on_an_engine_without_embeddings(tts_service_client) -> None:
    client, server = tts_service_client
    answer = client.post("/api/tts/generate_audio", json={
        "text": "Hello.", "speaker": "voice-cloning:A", "provider": "fish-s2-pro",
        "speaker_blend": [{"speaker": "voice-cloning:A", "weight": 0.5}, {"speaker": "voice-cloning:B", "weight": 0.5}]})
    assert answer.status_code == 422 and answer.json()["error"] == "voice_blend_unsupported"


@pytest.fixture
def tts_service_client(monkeypatch):
    import sys

    sys.path.insert(0, "src")
    from fastapi.testclient import TestClient

    from services.tts import tts_server

    monkeypatch.setattr(tts_server, "_TTS_PROVIDER_NAME", "fish-s2-pro")
    monkeypatch.setattr(tts_server, "_TTS_PROVIDER", object())
    monkeypatch.setattr(tts_server, "_TTS_PROVIDER_ERROR", "")
    monkeypatch.setattr(tts_server, "_SWAP", {"fence": None, "engine": "", "restore": "", "interrupted": False})
    monkeypatch.setattr(tts_server.app, "user_middleware", [])
    monkeypatch.setattr(tts_server.app, "middleware_stack", None)
    return TestClient(tts_server.app), tts_server
