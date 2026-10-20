"""Voice Studio Phase 4: audio tools (isolation, enhancement) and opt-in watermarking.

The audio service's models are faked here; the real-model checks (SI-SDR of
isolation, AudioSeal detection after effects and lossy export) are recorded in
the roadmap.
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
from app.platform.voice import jobs as voice_jobs
from app.platform.voice.audio_service import AudioServiceUnavailable, Stems

RATE = 24_000


def _wav(seconds: float = 1.0, value: float = 0.2, rate: int = RATE) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(rate)
        time = np.arange(int(rate * seconds)) / rate
        target.writeframes((value * np.sin(2 * np.pi * 220 * time) * 32767).astype("<i2").tobytes())
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

    def mark_running(self, job_id: str) -> None:
        pass

    def complete_job(self, job_id: str, request: Any) -> None:
        self.completed[job_id] = request

    def fail_job(self, job_id: str, request: Any) -> None:
        self.failed[job_id] = request


class _Client:
    """The audio service, faked: marks append a byte so a test can see the audio passed through it."""

    def __init__(self, *, down: bool = False) -> None:
        self.down = down
        self.calls: list[tuple[str, Any]] = []

    def _check(self) -> None:
        if self.down:
            raise AudioServiceUnavailable("The audio service is not answering")

    def isolate(self, audio: bytes, filename: str, *, model: str = "roformer") -> Stems:
        self._check()
        self.calls.append(("isolate", model))
        return Stems(vocals=_wav(value=0.3), background=_wav(value=0.1), sample_rate=RATE, model="Mel-Band RoFormer")

    def enhance(self, audio: bytes, filename: str) -> tuple[bytes, dict[str, Any]]:
        self._check()
        self.calls.append(("enhance", filename))
        return _wav(value=0.25, rate=16_000), {"model": "GTCRN", "sample_rate": 16_000}

    def watermark(self, wav: bytes, *, message: int) -> tuple[bytes, dict[str, Any]]:
        self._check()
        self.calls.append(("watermark", message))
        return wav, {"model": "audioseal_wm_16bits", "message": message}

    def detect(self, audio: bytes, filename: str) -> dict[str, Any]:
        self._check()
        return {"probability": 0.99, "detected": True, "message": 1234}


def _job(job_type: str, payload: dict[str, Any], *, asset_id: str = "audio:mix") -> JobRecord:
    return JobRecord.model_validate({
        "id": f"job-{job_type.replace('.', '-')}", "module": "voice", "type": job_type, "status": "running",
        "resource_class": "gpu:audio", "input_payload": payload, "input_ref": {"asset_id": asset_id},
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
    source = tmp_path / "mix.wav"
    source.write_bytes(_wav())
    store.upsert_asset(AssetRecord(id="audio:mix", module="voice", type=AssetType.AUDIO, mime_type="audio/wav",
                                   storage_path=str(source), metadata={"title": "Interview"},
                                   created_at="2026-10-19T00:00:00+00:00"))
    return store


@pytest.fixture
def client(monkeypatch) -> _Client:
    fake = _Client()
    monkeypatch.setattr("app.platform.voice.audio_service.AudioServiceClient", lambda *args, **kwargs: fake)
    monkeypatch.setattr("app.platform.voice.audio_tools.AudioServiceClient", lambda *args, **kwargs: fake)
    return fake


@pytest.fixture
def watermark_on(monkeypatch) -> None:
    monkeypatch.setattr("app.platform.voice.watermarking.watermark_enabled", lambda: True)
    monkeypatch.setattr("app.platform.voice.watermarking.workspace_message", lambda: 1234)


# --- Audio tools ------------------------------------------------------------------------------


def test_isolation_stores_two_stems_whose_parent_is_the_source(stores, client) -> None:
    store = _JobStore()
    job = _job("audio.isolate", {"model": "demucs"})
    voice_jobs.execute_voice_studio_job(store, job)
    assert job.id in store.completed, store.failed.get(job.id)
    assert client.calls == [("isolate", "demucs")]
    refs = store.completed[job.id].output_refs
    assert [ref["kind"] for ref in refs] == ["stem_vocals", "stem_background"]
    for ref in refs:
        stem = stores.assets[ref["asset_id"]]
        assert stem.parent_asset_ids == ["audio:mix"] and stem.metadata["model"] == "Mel-Band RoFormer"
        assert ref["audio_url"] == f"/api/assets/{stem.id}/audio"
    assert stores.assets[refs[0]["asset_id"]].metadata["title"] == "Interview (vocals)"


def test_enhancement_and_detection_work_on_stored_assets(stores, client) -> None:
    store = _JobStore()
    job = _job("audio.enhance", {})
    voice_jobs.execute_voice_studio_job(store, job)
    enhanced = stores.assets[store.completed[job.id].output_refs[0]["asset_id"]]
    assert enhanced.metadata == {"title": "Interview (enhanced)", "kind": "enhanced", "enhancer": "GTCRN"}
    job = _job("audio.watermark-detect", {})
    voice_jobs.execute_voice_studio_job(store, job)
    check = store.completed[job.id].output_refs[0]
    assert check["detected"] is True and check["message"] == 1234


@pytest.mark.parametrize(("payload", "asset_id"), [
    ({"model": "spleeter"}, "audio:mix"),
    ({"source_path": "C:/Windows/win.ini"}, "audio:mix"),
    ({}, "audio:missing"),
])
def test_bad_audio_tool_requests_fail_without_retry(stores, client, payload: dict[str, Any], asset_id: str) -> None:
    store = _JobStore()
    job = _job("audio.isolate", payload, asset_id=asset_id)
    voice_jobs.execute_voice_studio_job(store, job)
    assert store.failed[job.id].code == "invalid_request" and store.failed[job.id].retryable is False
    assert client.calls == []


def test_a_down_service_fails_the_tool_so_it_can_be_retried(stores, monkeypatch) -> None:
    down = _Client(down=True)
    monkeypatch.setattr("app.platform.voice.audio_tools.AudioServiceClient", lambda *args, **kwargs: down)
    store = _JobStore()
    job = _job("audio.enhance", {})
    voice_jobs.execute_voice_studio_job(store, job)
    assert store.failed[job.id].code == "audio_service_unavailable" and store.failed[job.id].retryable is True


def test_the_audio_tool_jobs_run_on_the_audio_pool() -> None:
    from app.jobs.models import ResourceClass
    from app.platform.voice.feature import FEATURE

    classes = {spec.type: spec.resource_class for spec in FEATURE.job_handlers}
    assert {classes[name] for name in ("audio.isolate", "audio.enhance", "audio.watermark-detect")} == {ResourceClass.GPU_AUDIO}


# --- Cloning with isolation and enhancement ---------------------------------------------------


def test_cloning_can_isolate_and_enhance_the_sample_first(stores, client) -> None:
    store = _JobStore()
    payload = {"profile_name": "Host", "sample_audio_base64": base64.b64encode(_wav(seconds=6.0)).decode("ascii"),
               "source_file_name": "interview.mp3", "isolate_vocals": True, "enhance_sample": True,
               "reference_text": "hello", "quality": "Draft"}
    job = _job("voice-cloning.create-profile", payload)
    voice_jobs.execute_voice_studio_job(store, job)
    assert job.id in store.completed, store.failed.get(job.id)
    assert [call[0] for call in client.calls] == ["isolate", "enhance"]
    assert client.calls[1][1] == "vocals.wav"  # enhancement ran on the isolated voice
    voice = next(asset for asset in stores.assets.values() if asset.type == AssetType.VOICE_PROFILE)
    assert voice.metadata["sample_preparation"] == ["isolated vocals (Mel-Band RoFormer)", "enhanced (GTCRN)"]
    assert voice.storage_path.endswith(".wav")


# --- Watermarking -----------------------------------------------------------------------------


def test_watermarking_is_off_by_default(monkeypatch) -> None:
    from app.config.defaults import DEFAULT_SETTINGS
    from app.platform.voice import watermarking

    assert DEFAULT_SETTINGS["voice_watermark"] == {"enabled": False}
    monkeypatch.setattr("app.settings.access.load_settings", lambda: {})
    assert watermarking.mark(b"wav") == (b"wav", None)


def test_with_watermarking_on_a_render_is_marked_before_it_is_written(monkeypatch, watermark_on) -> None:
    from app.platform.voice import watermarking

    fake = _Client()
    marked, record = watermarking.mark(_wav(), client=fake)
    assert fake.calls == [("watermark", 1234)]
    assert record == {"scheme": "audioseal_wm_16bits", "message": 1234, "model": "audioseal_wm_16bits"}


def test_with_watermarking_on_and_no_service_nothing_unmarked_is_saved(stores, monkeypatch, watermark_on) -> None:
    from app.platform.voice import design

    class _Engine:
        def generate_audio(self, text: str, **kwargs: Any) -> dict[str, Any]:
            return {"success": True, "audio_base64": base64.b64encode(_wav()).decode("ascii"), "duration": 1.0}

    monkeypatch.setattr(design, "_design_engine", lambda: _Engine())
    monkeypatch.setattr("app.platform.voice.audio_service.AudioServiceClient", lambda *args, **kwargs: _Client(down=True))
    before = set(stores.assets)
    store = _JobStore()
    job = _job("voice.design", {"description": "a narrator", "seeds": [1]})
    voice_jobs.execute_voice_studio_job(store, job)
    assert store.failed[job.id].code == "watermark_unavailable"
    assert "nothing was saved" in store.failed[job.id].message
    assert set(stores.assets) == before


def test_design_candidates_carry_their_watermark_record(stores, client, monkeypatch, watermark_on) -> None:
    from app.platform.voice import design

    class _Engine:
        def generate_audio(self, text: str, **kwargs: Any) -> dict[str, Any]:
            return {"success": True, "audio_base64": base64.b64encode(_wav()).decode("ascii"), "duration": 1.0}

    monkeypatch.setattr(design, "_design_engine", lambda: _Engine())
    store = _JobStore()
    job = _job("voice.design", {"description": "a narrator", "seeds": [1]})
    voice_jobs.execute_voice_studio_job(store, job)
    candidate = stores.assets[store.completed[job.id].output_refs[0]["asset_id"]]
    assert candidate.metadata["watermark"]["message"] == 1234


def test_with_watermarking_on_export_refuses_an_unmarked_render(stores, monkeypatch, tmp_path: Path) -> None:
    render = tmp_path / "render.wav"
    render.write_bytes(_wav())
    for asset_id, metadata in (("audio:old", {"title": "Old"}),
                               ("audio:new", {"title": "New", "watermark": {"scheme": "audioseal_wm_16bits", "message": 1}})):
        stores.upsert_asset(AssetRecord(id=asset_id, module="voice", type=AssetType.AUDIO, mime_type="audio/wav",
                                        storage_path=str(render), metadata=metadata,
                                        created_at="2026-10-19T00:00:00+00:00",
                                        compat={"contract": "voice_studio_tts_v2"}))
    monkeypatch.setattr("app.platform.voice.watermarking.watermark_enabled", lambda: True)
    store = _JobStore()
    old = _job("voice.export", {"asset_id": "audio:old", "format": "wav16"}, asset_id="audio:old")
    voice_jobs.execute_voice_studio_job(store, old)
    assert "render it again" in store.failed[old.id].message
    new = _job("voice.export", {"asset_id": "audio:new", "format": "wav16"}, asset_id="audio:new")
    new = new.model_copy(update={"id": "job-export-new"})
    voice_jobs.execute_voice_studio_job(store, new)
    exported = stores.assets[store.completed[new.id].output_refs[0]["asset_id"]]
    assert exported.metadata["watermark"]["message"] == 1
    # A recording (not a render) exports either way.
    assert not __import__("app.platform.voice.watermarking", fromlist=["is_render"]).is_render(stores.assets["audio:mix"])


def test_the_workspace_message_is_a_stable_16_bit_hash(monkeypatch) -> None:
    from types import SimpleNamespace

    from app.platform.voice import watermarking

    monkeypatch.setattr("app.runtime.tenant_context.current_tenant", lambda: SimpleNamespace(workspace_id="ws-1"))
    first = watermarking.workspace_message()
    assert first == watermarking.workspace_message() and 0 <= first < 2 ** 16
    monkeypatch.setattr("app.runtime.tenant_context.current_tenant", lambda: SimpleNamespace(workspace_id="ws-2"))
    assert watermarking.workspace_message() != first


# --- The service ------------------------------------------------------------------------------


def test_watermark_messages_round_trip_through_bits() -> None:
    from services.audio import audio_server

    for message in (0, 1, 1234, 65535):
        assert audio_server.bits_message(audio_server.message_bits(message)) == message


def test_resampling_keeps_length_and_rate_ratio() -> None:
    pytest.importorskip("scipy")  # in the omnix-audio environment, not the gateway's
    from services.audio import audio_server

    samples = np.random.default_rng(1).standard_normal(48_000).astype(np.float32)
    assert len(audio_server.resample(samples, 48_000, 16_000)) == 16_000
    assert audio_server.resample(samples, 16_000, 16_000) is samples


def test_the_service_routes_validate_and_report_missing_models(monkeypatch) -> None:
    import secrets

    from fastapi.testclient import TestClient

    from services.audio import audio_server

    token = secrets.token_urlsafe(32)
    monkeypatch.setenv("OMNIX_SERVICE_TOKEN", token)

    def missing(*args: Any) -> Any:
        raise audio_server.ModelMissing("GTCRN could not be downloaded")

    monkeypatch.setattr(audio_server, "enhance", missing)
    monkeypatch.setattr(audio_server, "watermark", lambda payload, message: {"message": message})
    app_client = TestClient(audio_server.app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000),
                            headers={"X-Omnix-Service-Token": token, "X-Omnix-Client": "test"})
    response = app_client.post("/audio/enhance", files={"file": ("a.wav", _wav())})
    assert response.status_code == 200  # actionable outcomes survive the middleware as envelopes
    assert response.json() == {"ok": False, "code": "model_missing", "message": "GTCRN could not be downloaded"}
    assert app_client.post("/audio/isolate", files={"file": ("a.wav", _wav())}, data={"model": "x"}).status_code == 400
    assert app_client.post("/audio/watermark", files={"file": ("a.wav", _wav())}, data={"message": "70000"}).status_code == 400
    assert app_client.post("/audio/watermark", files={"file": ("a.wav", _wav())}, data={"message": "7"}).json() == {"message": 7}
    assert app_client.post("/audio/enhance", files={"file": ("a.wav", b"")}).status_code == 400


def test_the_client_tells_request_errors_from_outages(monkeypatch) -> None:
    from app.platform.voice.audio_service import AudioServiceClient, AudioToolRequestError

    monkeypatch.setenv("OMNIX_SERVICE_TOKEN", "t" * 48)

    class _Response:
        def __init__(self, status: int, body: dict[str, Any]) -> None:
            self.status_code = status
            self._body = body

        def json(self) -> dict[str, Any]:
            return self._body

    class _Http:
        def __init__(self, response: _Response) -> None:
            self.response = response

        def post(self, *args: Any, **kwargs: Any) -> _Response:
            return self.response

    missing = AudioServiceClient("http://audio", http=_Http(_Response(200, {"ok": False, "code": "model_missing", "message": "set it up"})))
    with pytest.raises(AudioToolRequestError, match="set it up"):
        missing.enhance(b"x", "a.wav")
    busy = AudioServiceClient("http://audio", http=_Http(_Response(200, {"ok": False, "code": "model_busy", "message": "VRAM"})))
    with pytest.raises(AudioServiceUnavailable, match="VRAM"):
        busy.enhance(b"x", "a.wav")
    refused = AudioServiceClient("http://audio", http=_Http(_Response(422, {"error": "invalid_request", "request_id": "r"})))
    with pytest.raises(AudioToolRequestError, match="invalid_request"):
        refused.enhance(b"x", "a.wav")
    crashed = AudioServiceClient("http://audio", http=_Http(_Response(500, {"error": "model_service_error", "request_id": "r"})))
    with pytest.raises(AudioServiceUnavailable):
        crashed.enhance(b"x", "a.wav")
    with pytest.raises(AudioServiceUnavailable, match="OMNIX_AUDIO_URL"):
        AudioServiceClient("", http=_Http(_Response(200, {}))).enhance(b"x", "a.wav")
