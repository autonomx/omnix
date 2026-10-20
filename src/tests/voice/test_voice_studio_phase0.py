"""Voice Studio Phase 0: every visible control changes the output or is refused clearly.

Covers engine pinning (no switching), the post-assembly effects chain, script
pauses through assembly, delivery instructions, export encoding and loudness,
stored-asset-only transcription, and clone sample cleanup.
"""
from __future__ import annotations

import base64
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import numpy as np
import pytest

from app.assets.models import AssetRecord, AssetType
from app.jobs.models import JobRecord
from app.platform.voice import effects, jobs as voice_jobs
from app.platform.voice.export import ExportRequestError, render_export
from app.platform.voice.loudness import integrated_loudness
from app.platform.voice.sample_cleanup import clean_sample, strictness_for
from app.providers.exceptions import TtsEngineNotLoaded

RATE = 24_000


def _tone(frequency: float = 220.0, seconds: float = 1.0, amplitude: float = 0.4, rate: int = RATE) -> np.ndarray:
    return amplitude * np.sin(2 * np.pi * frequency * np.arange(int(seconds * rate)) / rate)


def _wav(samples: np.ndarray, rate: int = RATE) -> bytes:
    return effects.write_mono(samples, rate)


def _band_energy(samples: np.ndarray, rate: int, low: float, high: float) -> float:
    spectrum = np.abs(np.fft.rfft(samples)) ** 2
    freqs = np.fft.rfftfreq(len(samples), 1.0 / rate)
    return float(spectrum[(freqs >= low) & (freqs <= high)].sum())


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

    def mark_running(self, job_id: str) -> None:
        pass

    def complete_job(self, job_id: str, request: Any) -> None:
        self.completed[job_id] = request

    def fail_job(self, job_id: str, request: Any) -> None:
        self.failed[job_id] = request


def _job(job_type: str, payload: dict[str, Any], *, module: str = "voice", input_ref: dict | None = None) -> JobRecord:
    return JobRecord.model_validate({
        "id": f"job-{job_type.replace('.', '-')}",
        "module": module,
        "type": job_type,
        "status": "running",
        "resource_class": "cpu",
        "input_payload": payload,
        "input_ref": input_ref,
        "created_at": "2026-10-19T00:00:00+00:00",
        "updated_at": "2026-10-19T00:00:00+00:00",
    })


@pytest.fixture
def stores(tmp_path: Path, monkeypatch) -> _AssetStore:
    import app.assets as assets_module

    store = _AssetStore()
    monkeypatch.setattr(assets_module, "default_asset_store", lambda: store)
    monkeypatch.setattr(voice_jobs, "default_asset_store", lambda: store)
    monkeypatch.setattr(voice_jobs, "resources_data_root", lambda: tmp_path)
    monkeypatch.setattr("app.runtime.paths.resources_data_root", lambda: tmp_path)
    return store


class _Engine:
    def __init__(self, name: str) -> None:
        self.provider_name = name
        self.calls: list[dict[str, Any]] = []

    def generate_audio(self, text: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"text": text, **kwargs})
        audio = base64.b64encode(_wav(_tone(seconds=0.5))).decode("ascii")
        return {"success": True, "audio": audio, "sample_rate": RATE, "duration": 0.5}


# --- Engine pinning -------------------------------------------------------------------------


def _in_process_runtime(monkeypatch, *, selected: str, loaded: str | None, instance: Any) -> None:
    from app.providers import service

    monkeypatch.setattr(service, "load_settings", lambda: {"audio_provider_tts": selected})
    monkeypatch.setattr(service, "get_runtime_config", lambda: SimpleNamespace(use_remote_tts=False, tts=None))
    monkeypatch.setattr(service, "_tts_provider_instance", instance)
    monkeypatch.setattr(service, "_tts_provider_name", loaded)
    monkeypatch.setattr(service, "get_tts_provider", lambda name=None: pytest.fail("pinning must not switch engines"))


def test_a_pinned_job_never_switches_the_loaded_engine(monkeypatch) -> None:
    from app.providers.service import pinned_tts_provider

    qwen = _Engine("faster-qwen3-tts")
    _in_process_runtime(monkeypatch, selected="faster-qwen3-tts", loaded="faster-qwen3-tts", instance=qwen)

    assert pinned_tts_provider("faster-qwen3-tts") is qwen
    assert pinned_tts_provider(None) is qwen
    with pytest.raises(TtsEngineNotLoaded) as refused:
        pinned_tts_provider("fish-s2-pro")
    assert refused.value.loaded == "faster-qwen3-tts"


def test_the_http_facade_asks_the_service_to_refuse_instead_of_switching(monkeypatch) -> None:
    from app.providers.qwen_http_gateway import QwenHttpGatewayProvider
    from tests.support.http import mock_http_client

    monkeypatch.setenv("OMNIX_SERVICE_TOKEN", "test-token-" + "x" * 32)
    sent: list[dict[str, Any]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(409, json={"error": "engine_not_loaded", "loaded": "faster-qwen3-tts"})

    facade = QwenHttpGatewayProvider("http://127.0.0.1:5101", provider_name="fish-s2-pro", require_loaded=True)
    facade.http = mock_http_client(handle)
    with pytest.raises(TtsEngineNotLoaded) as refused:
        facade.generate_audio("hello", speaker="Alex")
    assert sent[0]["require_loaded"] is True and sent[0]["provider"] == "fish-s2-pro"
    assert refused.value.loaded == "faster-qwen3-tts"


def test_the_tts_service_answers_409_instead_of_switching(monkeypatch) -> None:
    sys.path.insert(0, "src")
    from services.tts import tts_server

    monkeypatch.setattr(tts_server, "_TTS_PROVIDER_NAME", "faster-qwen3-tts")
    monkeypatch.setattr(tts_server, "_ensure_provider", lambda name: pytest.fail("must not switch"))
    response = tts_server._generate_audio(tts_server.TtsGenerateRequest(
        text="hello", provider="fish-s2-pro", require_loaded=True,
    ))
    assert response.status_code == 409
    assert json.loads(response.body)["loaded"] == "faster-qwen3-tts"


def test_an_engine_mismatch_fails_the_job_without_retries(monkeypatch, stores) -> None:
    def refuse(name: str | None = None) -> Any:
        raise TtsEngineNotLoaded("fish-s2-pro", loaded="faster-qwen3-tts")

    monkeypatch.setattr("app.providers.service.pinned_tts_provider", refuse)
    store = _JobStore()
    job = _job("tts.synthesize", {"text": "dave: hi", "provider_id": "tts:fish-s2-pro"})
    voice_jobs.execute_voice_studio_job(store, job)
    failure = store.failed[job.id]
    assert failure.code == "engine_not_loaded" and failure.retryable is False
    assert "select it in Voice Studio" in failure.message


# --- The render: grammar, assembly, delivery, effects --------------------------------------


def test_a_render_uses_pauses_delivery_and_effects_on_the_whole_take(monkeypatch, stores) -> None:
    fish = _Engine("fish-s2-pro")
    monkeypatch.setattr("app.providers.service.pinned_tts_provider", lambda name=None: fish)
    store = _JobStore()
    job = _job("tts.multi_speaker_synthesize", {
        "text": "dave: one\n{pause 600ms}\nbob: two",
        "provider_id": "fish-s2-pro",
        "character_voice_assignments": [
            {"speaker": "dave", "voice_id": "", "delivery_instruction": "whispering"},
            {"speaker": "bob", "voice_id": "", "style": "Calm"},
        ],
        "audio_effects": ["eq", "reverb", "Noise Reduction"],
        "output_settings": {"volume": -3.0},
    })
    voice_jobs.execute_voice_studio_job(store, job)
    assert job.id in store.completed, store.failed.get(job.id)

    # Delivery reaches the engine only for the speaker who has one; style stays a label.
    assert fish.calls[0]["instruct"] == "whispering"
    assert "instruct" not in fish.calls[1]
    asset = next(asset for asset in stores.assets.values() if asset.type == AssetType.AUDIO)
    metadata = asset.metadata
    assert metadata["rendered_engine"] == "fish-s2-pro"
    assert metadata["audio_effects"] == ["eq", "reverb"]  # chain order; labels are off
    assert metadata["volume_db"] == -3.0
    assert metadata["timeline"][1]["pause_before"] == pytest.approx(0.6, abs=0.001)
    # Reverb extends the take past the two 0.5 s segments and the pause.
    assert metadata["duration"] > 0.5 + 0.6 + 0.5 + 0.3


def test_qwen_never_receives_a_delivery_instruction(monkeypatch, stores) -> None:
    qwen = _Engine("faster-qwen3-tts")
    monkeypatch.setattr("app.providers.service.pinned_tts_provider", lambda name=None: qwen)
    store = _JobStore()
    job = _job("tts.synthesize", {
        "text": "dave: hi",
        "provider_id": "faster-qwen3-tts",
        "character_voice_assignments": [{"speaker": "dave", "delivery_instruction": "shouting"}],
    })
    voice_jobs.execute_voice_studio_job(store, job)
    assert job.id in store.completed
    assert "instruct" not in qwen.calls[0]


def test_old_effect_labels_leave_a_render_unprocessed(monkeypatch, stores) -> None:
    engine = _Engine("faster-qwen3-tts")
    monkeypatch.setattr("app.providers.service.pinned_tts_provider", lambda name=None: engine)
    store = _JobStore()
    job = _job("tts.synthesize", {"text": "hi", "audio_effects": ["Compression", "De-esser"]})
    voice_jobs.execute_voice_studio_job(store, job)
    asset = next(asset for asset in stores.assets.values() if asset.type == AssetType.AUDIO)
    assert asset.metadata["audio_effects"] == []


def test_each_effect_changes_a_test_signal_measurably() -> None:
    rate = 48_000
    rumble_and_voice = _tone(40.0, rate=rate) + _tone(1000.0, rate=rate)
    assert _band_energy(effects.equalize(rumble_and_voice, rate), rate, 20, 60) < \
        0.5 * _band_energy(rumble_and_voice, rate, 20, 60)

    sibilant = _tone(7000.0, amplitude=0.5, rate=rate) + _tone(300.0, amplitude=0.3, rate=rate)
    assert _band_energy(effects.deess(sibilant, rate), rate, 6500, 7500) < \
        0.5 * _band_energy(sibilant, rate, 6500, 7500)

    dynamic = np.concatenate([_tone(440.0, amplitude=0.05, rate=rate), _tone(440.0, amplitude=0.9, rate=rate)])
    compressed = effects.compress(dynamic, rate)
    loud_to_quiet = lambda samples: np.abs(samples[rate:]).max() / np.abs(samples[:rate]).max()  # noqa: E731
    assert loud_to_quiet(compressed) < 0.7 * loud_to_quiet(dynamic)

    click = np.zeros(rate)
    click[100] = 1.0
    wet = effects.reverb(click, rate)
    assert len(wet) > len(click)
    assert np.abs(wet[rate // 4: rate // 2]).max() > 1e-4  # a tail where the dry signal is silent

    assert effects.effect_ids(["Reverb", "eq", "compressor", "eq"]) == ["eq", "compressor"]


# --- Export -------------------------------------------------------------------------------


@pytest.mark.parametrize(("fmt", "rate"), [("mp3", 44_100), ("opus", 48_000), ("flac", 22_050), ("wav24", 24_000)])
def test_exports_decode_at_the_requested_rate(fmt: str, rate: int) -> None:
    import soundfile as sf

    encoded, details = render_export(_wav(_tone(seconds=1.0)), fmt=fmt, sample_rate=rate)
    decoded, decoded_rate = sf.read(io.BytesIO(encoded))
    assert decoded_rate == rate == details["sample_rate"]
    assert abs(len(decoded) / decoded_rate - 1.0) < 0.1


def test_opus_refuses_rates_it_cannot_encode() -> None:
    with pytest.raises(ExportRequestError, match="44100"):
        render_export(_wav(_tone()), fmt="opus", sample_rate=44_100)


def test_a_loudness_preset_reaches_its_target() -> None:
    import soundfile as sf

    encoded, details = render_export(_wav(_tone(seconds=3.0, amplitude=0.05)), fmt="wav16", loudness="podcast")
    decoded, rate = sf.read(io.BytesIO(encoded))
    assert details["target_lufs"] == -16.0
    assert integrated_loudness(decoded, rate) == pytest.approx(-16.0, abs=0.3)


def test_the_export_job_writes_a_child_asset(stores, tmp_path: Path) -> None:
    source_path = tmp_path / "take.wav"
    source_path.write_bytes(_wav(_tone()))
    stores.upsert_asset(AssetRecord(id="audio:take", module="voice", type=AssetType.AUDIO, mime_type="audio/wav",
                                    storage_path=str(source_path), metadata={"title": "take"},
                                    created_at="2026-10-19T00:00:00+00:00"))
    store = _JobStore()
    job = _job("voice.export", {"asset_id": "audio:take", "format": "mp3", "sample_rate": 44_100})
    voice_jobs.execute_voice_studio_job(store, job)
    assert job.id in store.completed, store.failed.get(job.id)
    exported = next(asset for asset in stores.assets.values() if asset.type == AssetType.EXPORT)
    assert exported.parent_asset_ids == ["audio:take"] and exported.mime_type == "audio/mpeg"


def test_a_bad_export_request_is_not_retried(stores) -> None:
    store = _JobStore()
    job = _job("voice.export", {"asset_id": "audio:missing", "format": "mp3"})
    voice_jobs.execute_voice_studio_job(store, job)
    assert store.failed[job.id].retryable is False


# --- Transcription ------------------------------------------------------------------------


def test_transcription_takes_stored_assets_never_server_paths(stores) -> None:
    store = _JobStore()
    job = _job("stt.transcribe", {"source_path": "C:/Windows/win.ini"}, module="stt")
    voice_jobs.execute_voice_studio_job(store, job)
    assert store.failed[job.id].code == "invalid_request"
    assert store.failed[job.id].retryable is False


@pytest.mark.parametrize("save", [True, False])
def test_transcription_saves_a_transcript_only_when_asked(monkeypatch, stores, tmp_path: Path, save: bool) -> None:
    audio_path = tmp_path / "clip.wav"
    audio_path.write_bytes(_wav(_tone()))
    stores.upsert_asset(AssetRecord(id="audio:clip", module="voice", type=AssetType.AUDIO, mime_type="audio/wav",
                                    storage_path=str(audio_path), created_at="2026-10-19T00:00:00+00:00"))

    class _Stt:
        provider_name = "parakeet"

        def transcribe(self, path: str, language: str | None = None) -> dict[str, Any]:
            assert language is None  # the batch engine is English-only until Phase 2
            return {"success": True, "text": "hello world", "segments": [], "duration": 1.0}

    monkeypatch.setattr("app.providers.service.get_stt_provider", lambda name=None: _Stt())
    store = _JobStore()
    job = _job("stt.transcribe", {"save_transcript": save}, module="stt", input_ref={"asset_id": "audio:clip"})
    voice_jobs.execute_voice_studio_job(store, job)
    assert job.id in store.completed, store.failed.get(job.id)
    transcripts = [asset for asset in stores.assets.values() if asset.type == AssetType.TRANSCRIPT]
    assert len(transcripts) == (1 if save else 0)
    if save:
        assert transcripts[0].parent_asset_ids == ["audio:clip"]


# --- Clone sample cleanup -----------------------------------------------------------------


def test_a_clone_sample_is_trimmed_leveled_and_checked() -> None:
    rate = 24_000
    rng = np.random.default_rng(1)
    voice = np.concatenate([np.zeros(rate), _tone(200.0, seconds=6.0, rate=rate), np.zeros(rate)])
    noisy = voice + 0.04 * rng.standard_normal(len(voice))
    cleaned, suffix, report = clean_sample(_wav(noisy, rate), quality="High")
    assert suffix == ".wav" and report.checked
    assert report.trimmed_seconds > 1.5
    assert report.loudness_lufs == pytest.approx(-20.0, abs=0.5)
    assert any("Background noise" in warning for warning in report.warnings)
    decoded, _ = effects.read_mono(cleaned)
    assert len(decoded) / rate < 7.0


def test_an_unreadable_recording_passes_through_unchecked() -> None:
    webm = b"\x1aE\xdf\xa3" + b"\x00" * 64
    cleaned, suffix, report = clean_sample(webm, quality="Draft")
    assert cleaned == webm and suffix is None and not report.checked


def test_quality_labels_map_to_check_strictness() -> None:
    assert strictness_for("High (Recommended)") == "high"
    assert strictness_for("Standard") == "standard"
    assert strictness_for("Fast Preview") == "draft"


def test_a_peaky_take_still_reaches_its_loudness_target_under_the_ceiling() -> None:
    """Plain gain would stop at the peak ceiling short of the target; the limiter gets there."""
    import soundfile as sf

    rate = 24_000
    speech = _tone(220.0, seconds=4.0, amplitude=0.05, rate=rate)
    speech[rate: rate + 200] = 0.95  # a click far above the speech level
    encoded, details = render_export(_wav(speech, rate), fmt="wav16", loudness="podcast")
    decoded, decoded_rate = sf.read(io.BytesIO(encoded))
    assert integrated_loudness(decoded, decoded_rate) == pytest.approx(-16.0, abs=0.3)
    assert np.abs(decoded).max() <= 10 ** (-1.0 / 20) + 1e-3
    assert details["output_lufs"] == pytest.approx(-16.0, abs=0.3)
