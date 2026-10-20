"""Voice Studio Phase 1 without PostgreSQL: model installs, the TTS service's swap endpoints, swap deferral."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.platform.voice import model_install
from app.platform.voice.model_catalog import SPEECH_MODELS, speech_model


@pytest.fixture
def models_dir(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setattr(model_install, "models_root", lambda: tmp_path / "models")
    monkeypatch.setattr(model_install, "_hub_token", lambda: "hf_test")
    return tmp_path / "models"


class _Hub:
    """Stands in for ``huggingface_hub``: pins a commit and writes the snapshot."""

    def __init__(self) -> None:
        self.downloads: list[dict[str, Any]] = []

    def HfApi(self):  # noqa: N802 - the real module's spelling
        return SimpleNamespace(model_info=lambda repo_id, revision, token: SimpleNamespace(sha="abc123"))

    def snapshot_download(self, *, repo_id: str, revision: str, local_dir: str, token: str | None,
                          allow_patterns: list[str] | None = None) -> str:
        self.downloads.append({"repo_id": repo_id, "revision": revision, "token": token})
        Path(local_dir, "model.safetensors").write_bytes(b"weights")
        return local_dir


def test_the_catalog_names_each_model_once_with_its_licence() -> None:
    ids = [model.id for model in SPEECH_MODELS]
    assert len(ids) == len(set(ids))
    assert all(model.licence and model.licence_url for model in SPEECH_MODELS)
    assert speech_model("sortformer-4spk-v1").requires_acceptance  # CC-BY-NC-4.0
    assert not speech_model("qwen3-tts-1.7b-voicedesign").requires_acceptance


def test_an_install_pins_its_commit_and_records_licence_and_terms(models_dir: Path) -> None:
    hub = _Hub()
    status = model_install.install_model("qwen3-tts-1.7b-voicedesign", hub=hub)
    assert status["status"] == "installed" and status["installed_revision"] == "abc123"
    assert hub.downloads == [{"repo_id": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign", "revision": "abc123", "token": "hf_test"}]
    marker = json.loads((models_dir / "tts" / "Qwen3-TTS-12Hz-1.7B-VoiceDesign" / model_install.MARKER).read_text())
    assert marker["licence"] == "Apache-2.0" and marker["commit"] == "abc123"


def test_non_commercial_models_need_their_terms_accepted(models_dir: Path) -> None:
    with pytest.raises(model_install.ModelInstallError, match="accept its terms"):
        model_install.install_model("sortformer-4spk-v1", hub=_Hub())
    status = model_install.install_model("sortformer-4spk-v1", accept_terms=True, hub=_Hub())
    assert status["accepted_terms"] is True


def test_package_models_are_not_installed_here(models_dir: Path) -> None:
    with pytest.raises(model_install.ModelInstallError, match="own package"):
        model_install.install_model("htdemucs-ft", hub=_Hub())
    assert model_install.model_status(speech_model("htdemucs-ft"))["status"] == "package"


def test_remove_deletes_only_inside_the_models_folder(models_dir: Path) -> None:
    model_install.install_model("qwen3-tts-1.7b-voicedesign", hub=_Hub())
    status = model_install.remove_model("qwen3-tts-1.7b-voicedesign")
    assert status["status"] == "missing"
    assert not (models_dir / "tts" / "Qwen3-TTS-12Hz-1.7B-VoiceDesign").exists()


def test_installs_are_for_workspace_admins_only(monkeypatch) -> None:
    from app.jobs.models import CreateJobRequest, ResourceClass
    from app.platform.voice.feature import voice_submission_defaults
    from app.runtime.tenant_context import TenantAccessDenied, TenantContext, pop_tenant, push_tenant

    request = CreateJobRequest(module="voice", type="models.install", resource_class=ResourceClass.CPU,
                               input_payload={"model_id": "qwen3-tts-1.7b-voicedesign"})
    member = TenantContext(user_id="user:a", workspace_id="workspace:a", membership_id="m:a", roles=frozenset({"member"}))
    token = push_tenant(member)
    try:
        with pytest.raises(TenantAccessDenied):
            voice_submission_defaults(request)
    finally:
        pop_tenant(token)
    admin = TenantContext(user_id="user:a", workspace_id="workspace:a", membership_id="m:a", roles=frozenset({"admin"}))
    token = push_tenant(admin)
    try:
        assert voice_submission_defaults(request).type == "models.install"
    finally:
        pop_tenant(token)


def test_a_member_is_refused_admin_actions_with_403_not_a_server_error() -> None:
    from types import SimpleNamespace

    from fastapi import APIRouter, FastAPI, HTTPException
    from fastapi.testclient import TestClient

    from app.composition.gateway.kernel_routes.core_jobs_routes import register_core_jobs_routes
    from app.platform.voice.voice_studio_routes import _require_admin
    from app.runtime.tenant_context import TenantAccessDenied, TenantContext, pop_tenant, push_tenant

    def refuse(request: Any) -> Any:
        raise TenantAccessDenied("workspace admin role required")

    router = APIRouter()
    state = SimpleNamespace(job_handler_registry=SimpleNamespace(validate_submission=refuse))
    register_core_jobs_routes(router, state, get_chat_store=lambda: None,
                              get_job_store=lambda: pytest.fail("a refused job must not be stored"))
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).post("/api/jobs", json={
        "module": "voice", "type": "models.install", "resource_class": "cpu",
        "input_payload": {"model_id": "qwen3-tts-1.7b-voicedesign"}})
    assert response.status_code == 403 and response.json()["detail"] == "job_submission_forbidden"

    member = TenantContext(user_id="user:a", workspace_id="workspace:a", membership_id="m:a", roles=frozenset({"member"}))
    token = push_tenant(member)
    try:
        with pytest.raises(HTTPException) as refused:
            _require_admin()
        assert refused.value.status_code == 403
    finally:
        pop_tenant(token)


# --- The TTS service's swap endpoints --------------------------------------------------------


@pytest.fixture
def tts_service(monkeypatch):
    sys.path.insert(0, "src")
    from fastapi.testclient import TestClient

    from services.tts import tts_server

    loaded = {"name": "faster-qwen3-tts"}

    def select(name: str, *, realtime: bool = False) -> dict[str, Any]:
        loaded["name"] = name
        monkeypatch.setattr(tts_server, "_TTS_PROVIDER_NAME", name)
        return {"ok": True, "provider": name, "details": {}}

    monkeypatch.setattr(tts_server, "_TTS_PROVIDER_NAME", "faster-qwen3-tts")
    monkeypatch.setattr(tts_server, "select_tts_provider", select)
    monkeypatch.setattr(tts_server, "_SWAP", {"fence": None, "engine": "", "restore": "", "interrupted": False})
    monkeypatch.setattr(tts_server.app, "user_middleware", [])
    monkeypatch.setattr(tts_server.app, "middleware_stack", None)
    return TestClient(tts_server.app), tts_server, loaded


def test_a_fenced_swap_refuses_other_requests_until_restored(tts_service) -> None:
    client, server, loaded = tts_service
    swapped = client.post("/api/tts/engine/swap", json={"provider": "fish-s2-pro", "fence_token": 3,
                                                        "restore_provider": "faster-qwen3-tts"})
    assert swapped.status_code == 200 and loaded["name"] == "fish-s2-pro"
    with pytest.raises(server.EngineSwapped):
        server._ensure_provider("faster-qwen3-tts")  # an audiobook render waits
    assert client.post("/api/tts/provider", json={"provider": "faster-qwen3-tts"}).status_code == 409
    assert client.post("/api/tts/engine/restore", json={"provider": "faster-qwen3-tts", "fence_token": 2}).status_code == 409
    restored = client.post("/api/tts/engine/restore", json={"provider": "faster-qwen3-tts", "fence_token": 3})
    assert restored.status_code == 200 and loaded["name"] == "faster-qwen3-tts"
    assert server._swap_snapshot()["fence"] is None


def test_a_request_for_the_engine_being_loaded_waits_instead_of_failing(tts_service, monkeypatch) -> None:
    """While a swapped-in engine loads, its pinned job gets 409 (and waits), not a 500."""
    client, server, _loaded = tts_service
    monkeypatch.setattr(server, "_TTS_PROVIDER_NAME", "fish-s2-pro")
    monkeypatch.setattr(server, "_TTS_PROVIDER", None)
    monkeypatch.setattr(server, "_TTS_PROVIDER_ERROR", "switching to fish-s2-pro")
    answer = client.post("/api/tts/generate_audio", json={"text": "Hello.", "speaker": "default", "language": "en",
                                                         "provider": "fish-s2-pro", "require_loaded": True})
    assert answer.status_code == 409 and answer.json()["error"] == "engine_loading"


def test_live_speech_interrupts_a_swap(tts_service) -> None:
    client, server, loaded = tts_service
    client.post("/api/tts/engine/swap", json={"provider": "fish-s2-pro", "fence_token": 1, "restore_provider": "faster-qwen3-tts"})
    server._ensure_provider("faster-qwen3-tts", realtime=True)
    assert loaded["name"] == "faster-qwen3-tts"
    snapshot = server._swap_snapshot()
    assert snapshot["fence"] is None and snapshot["interrupted"] is True


@pytest.fixture
def engine_switching(monkeypatch):
    """The real ``select_tts_provider`` over fake engines, with a clean in-flight count."""
    sys.path.insert(0, "src")
    from types import SimpleNamespace

    from services.tts import tts_server

    stopped: list[str] = []

    def engine(name: str) -> Any:
        return SimpleNamespace(provider_name=name, stop=lambda: stopped.append(name))

    def initialize(name: str | None = None) -> dict[str, Any]:
        monkeypatch.setattr(tts_server, "_TTS_PROVIDER", engine(str(name)))
        monkeypatch.setattr(tts_server, "_TTS_PROVIDER_NAME", str(name))
        return {"ok": True, "provider": name, "details": {}}

    monkeypatch.setattr(tts_server, "initialize_tts_provider", initialize)
    monkeypatch.setattr(tts_server, "_TTS_MODEL_OWNER_GUARD", None)
    monkeypatch.setattr(tts_server, "_TTS_PROVIDER", engine("faster-qwen3-tts"))
    monkeypatch.setattr(tts_server, "_TTS_PROVIDER_NAME", "faster-qwen3-tts")
    monkeypatch.setattr(tts_server, "_IN_FLIGHT_COUNT", 0)
    monkeypatch.setattr(tts_server, "_DRAINING", False)
    monkeypatch.setattr(tts_server, "_URGENT_SWITCHES", 0)
    monkeypatch.setattr(tts_server, "SWITCH_DRAIN_SECONDS", 30)
    return tts_server, stopped


def _wait_until(condition: Any, seconds: float = 5.0) -> None:
    import time

    deadline = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.01)


def test_a_switch_lets_a_running_generation_finish_before_unloading_its_engine(engine_switching) -> None:
    import threading

    server, stopped = engine_switching
    server._begin_generation()  # a render is running on Qwen3
    switch = threading.Thread(target=server.select_tts_provider, args=("fish-s2-pro",))
    switch.start()
    _wait_until(lambda: server._DRAINING)
    assert stopped == [] and server._TTS_PROVIDER_NAME == "faster-qwen3-tts"
    with pytest.raises(server.EngineLoading):
        server._begin_generation()  # a new render waits for the next engine
    server._begin_generation(realtime=True)  # live speech still gets in
    server._end_generation()
    server._end_generation()  # the render finishes
    switch.join(timeout=5)
    assert not switch.is_alive()
    assert stopped == ["faster-qwen3-tts"] and server._TTS_PROVIDER_NAME == "fish-s2-pro"
    assert not server._DRAINING


def test_live_speech_never_waits_for_running_generations(engine_switching) -> None:
    import threading

    server, stopped = engine_switching
    server._begin_generation()  # a render that will not finish during this test
    switch = threading.Thread(target=server.select_tts_provider, args=("fish-s2-pro",))
    switch.start()
    _wait_until(lambda: server._DRAINING)
    live = threading.Thread(target=server.select_tts_provider, args=("faster-qwen3-tts",), kwargs={"realtime": True})
    live.start()
    switch.join(timeout=5)
    live.join(timeout=5)
    assert not switch.is_alive() and not live.is_alive()  # the waiting switch was cut short, not timed out
    assert server._TTS_PROVIDER_NAME == "faster-qwen3-tts" and stopped == ["faster-qwen3-tts", "fish-s2-pro"]
    server._end_generation()


def test_a_render_asked_for_during_a_switch_hears_engine_loading(tts_service, monkeypatch) -> None:
    from types import SimpleNamespace

    client, server, _loaded = tts_service
    monkeypatch.setattr(server, "_TTS_PROVIDER", SimpleNamespace(provider_name="faster-qwen3-tts"))
    monkeypatch.setattr(server, "_DRAINING", True)
    answer = client.post("/api/tts/generate_audio", json={"text": "Hello.", "speaker": "default", "language": "en",
                                                         "provider": "faster-qwen3-tts", "require_loaded": True})
    assert answer.status_code == 409 and answer.json()["error"] == "engine_loading"


# --- Swap deferral in the TTS job ------------------------------------------------------------


def test_a_job_for_an_unloaded_engine_asks_for_a_swap_and_waits(monkeypatch) -> None:
    from app.jobs.models import JobRecord
    from app.platform.voice import jobs as voice_jobs
    from app.providers.exceptions import TtsEngineNotLoaded

    requested: list[tuple[str, str]] = []
    monkeypatch.setattr("app.platform.voice.swap_controller.swaps_enabled", lambda: True)
    monkeypatch.setattr("app.persistence.tts_swap.request_swap", lambda engine, job_id: requested.append((engine, job_id)))
    monkeypatch.setattr("app.persistence.tts_swap.swap_request_failure", lambda job_id: None)
    monkeypatch.setattr("app.persistence.tts_swap.swap_wait_seconds", lambda job_id: 0.0)
    monkeypatch.setattr("app.persistence.tts_swap.finish_swap_request", lambda job_id: None)

    def refuse(name: str | None = None) -> Any:
        raise TtsEngineNotLoaded("fish-s2-pro", loaded="faster-qwen3-tts")

    monkeypatch.setattr("app.providers.service.pinned_tts_provider", refuse)

    class _Store:
        deferred: list[dict[str, Any]] = []

        def mark_running(self, job_id: str) -> None:
            pass

        def defer_job(self, job_id: str, **kwargs: Any) -> Any:
            self.deferred.append({"job_id": job_id, **kwargs})
            return None

        def fail_job(self, job_id: str, request: Any) -> Any:
            pytest.fail(f"a job waiting for a swap must not fail: {request.message}")

    job = JobRecord.model_validate({
        "id": "job:fish", "module": "voice", "type": "tts.synthesize", "status": "running", "resource_class": "gpu:tts",
        "input_payload": {"text": "dave: hi", "provider_id": "fish-s2-pro"},
        "created_at": "2026-10-20T00:00:00+00:00", "updated_at": "2026-10-20T00:00:00+00:00",
    })
    store = _Store()
    voice_jobs.execute_voice_studio_job(store, job)
    assert requested == [("fish-s2-pro", "job:fish")]
    assert store.deferred[0]["job_id"] == "job:fish" and "fish-s2-pro" in store.deferred[0]["reason"]


def test_a_failed_swap_request_fails_the_job_with_its_reason(monkeypatch) -> None:
    from app.jobs.models import JobRecord
    from app.platform.voice import jobs as voice_jobs
    from app.providers.exceptions import TtsEngineNotLoaded

    monkeypatch.setattr("app.platform.voice.swap_controller.swaps_enabled", lambda: True)
    monkeypatch.setattr("app.persistence.tts_swap.swap_request_failure", lambda job_id: "needs 12 GB of VRAM")
    monkeypatch.setattr("app.persistence.tts_swap.finish_swap_request", lambda job_id: None)
    monkeypatch.setattr("app.providers.service.pinned_tts_provider",
                        lambda name=None: (_ for _ in ()).throw(TtsEngineNotLoaded("fish-s2-pro")))

    failures: list[Any] = []

    class _Store:
        def mark_running(self, job_id: str) -> None:
            pass

        def defer_job(self, job_id: str, **kwargs: Any) -> Any:
            pytest.fail("a failed swap must not wait again")

        def fail_job(self, job_id: str, request: Any) -> Any:
            failures.append(request)

    job = JobRecord.model_validate({
        "id": "job:big", "module": "voice", "type": "tts.synthesize", "status": "running", "resource_class": "gpu:tts",
        "input_payload": {"text": "hi", "provider_id": "fish-s2-pro"},
        "created_at": "2026-10-20T00:00:00+00:00", "updated_at": "2026-10-20T00:00:00+00:00",
    })
    voice_jobs.execute_voice_studio_job(_Store(), job)
    assert failures[0].code == "engine_not_loaded" and not failures[0].retryable
    assert "needs 12 GB" in failures[0].message


def test_a_swap_to_an_engine_the_host_cannot_hold_fails_fast_with_a_reason() -> None:
    from app.platform.voice.swap_controller import ServiceHealth, SwapController

    gb = 1024 ** 3
    short = ServiceHealth(loaded_engine="faster-qwen3-tts", swap_fence=None, host_free_bytes=10 * gb)
    assert "24 GB of free host memory" in SwapController._host_shortfall("fish-s2-pro", short)
    assert SwapController._host_shortfall("fish-s2-pro", ServiceHealth("faster-qwen3-tts", None, host_free_bytes=30 * gb)) == ""
    # In-process engines need no host check, and leaving Fish frees its own process's memory.
    assert SwapController._host_shortfall("qwen3-tts-voicedesign", short) == ""
    assert SwapController._host_shortfall("fish-s2-pro", ServiceHealth("fish-s2-pro", None, host_free_bytes=2 * gb)) == ""
    # Unloading VoiceDesign gives back about 1.5 GB of the TTS process's memory: 25 + 1.5 is enough.
    assert SwapController._host_shortfall(
        "fish-s2-pro", ServiceHealth("qwen3-tts-voicedesign", None, host_free_bytes=25 * gb)) == ""


def test_fish_refuses_to_start_without_the_host_memory_it_needs(monkeypatch, tmp_path) -> None:
    from app.providers import fish_s2_pro_provider, host_memory

    monkeypatch.setattr(host_memory, "available_commit_bytes", lambda: 3 * 1024 ** 3)
    launched: list[object] = []
    stopped: list[int] = []
    monkeypatch.setattr(fish_s2_pro_provider.subprocess, "Popen", lambda *args, **kwargs: launched.append(args))
    monkeypatch.setattr(fish_s2_pro_provider, "_stop_process_tree", stopped.append)
    provider = fish_s2_pro_provider.FishS2ProTTSProvider({"checkpoint_dir": str(tmp_path)})
    monkeypatch.setattr(provider, "_server_healthy", lambda: False)
    # A Fish server another TTS service runs (its pid file is shared): a refused start must not stop it.
    pid_file = tmp_path / "fish-s2-pro.pid"
    pid_file.write_text("4242", encoding="utf-8")
    monkeypatch.setattr(provider, "_pid_path", lambda: pid_file)
    result = provider.start()
    assert result["running"] is False and "24 GB of free host memory" in result["error"]
    assert launched == [] and stopped == []


def test_a_failed_restore_keeps_the_swap_open(tts_service, monkeypatch) -> None:
    client, server, _loaded = tts_service
    client.post("/api/tts/engine/swap", json={"provider": "fish-s2-pro", "fence_token": 4,
                                              "restore_provider": "faster-qwen3-tts"})
    monkeypatch.setattr(server, "select_tts_provider", lambda name: {"ok": False, "error": "host memory is short",
                                                                     "provider": name, "details": {}})
    refused = client.post("/api/tts/engine/restore", json={"provider": "faster-qwen3-tts", "fence_token": 4})
    assert refused.status_code == 503
    assert server._swap_snapshot()["fence"] == 4   # the controller's retry finds its swap


def test_a_job_stops_waiting_for_its_engine_after_the_limit(monkeypatch) -> None:
    from types import SimpleNamespace

    from app.platform.voice import jobs as voice_jobs
    from app.providers.exceptions import TtsEngineNotLoaded

    monkeypatch.setattr("app.platform.voice.swap_controller.swaps_enabled", lambda: True)
    monkeypatch.setattr("app.persistence.tts_swap.swap_request_failure", lambda job_id: None)
    monkeypatch.setattr("app.persistence.tts_swap.swap_wait_seconds", lambda job_id: 0.0)
    waited = {"job:old": 3600.0, "job:new": 10.0}
    monkeypatch.setattr("app.persistence.tts_swap.swap_wait_seconds", lambda job_id: waited[job_id])
    requested: list[str] = []
    monkeypatch.setattr("app.persistence.tts_swap.request_swap", lambda engine, job_id: requested.append(engine))
    store = SimpleNamespace(defer_job=lambda job_id, **kwargs: None)
    exc = TtsEngineNotLoaded("fish-s2-pro")
    assert voice_jobs._defer_for_swap(store, SimpleNamespace(id="job:old"), exc) is None
    assert "within 30 minutes" in str(exc) and requested == []
    fresh = SimpleNamespace(id="job:new")
    assert voice_jobs._defer_for_swap(store, fresh, TtsEngineNotLoaded("fish-s2-pro")) is fresh
    assert requested == ["fish-s2-pro"]
