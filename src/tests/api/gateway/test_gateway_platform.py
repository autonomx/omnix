"""Representative platform contract tests for settings, reports, and diagnostics."""
from __future__ import annotations

import sys
from uuid import uuid4
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


SRC_DIR = Path(__file__).resolve().parents[3]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _client(settings_service=None) -> TestClient:
    app = _test_gateway_app()

    if settings_service is not None:
        app.state.runtime_services.settings = settings_service
    return TestClient(
        app,
        base_url="http://127.0.0.1",
        raise_server_exceptions=False,
        headers={"X-Omnix-Client": "test"},
    )


def _test_gateway_app(**kwargs):
    from app.platform.chat import InMemoryChatSessionStore
    from app.composition.gateway.main import create_gateway_app
    from app.jobs import InMemoryModelResidencyStore
    from tests.support.in_memory_jobs import InMemoryJobStore

    test_id = uuid4().hex
    kwargs.setdefault(
        "chat_store_factory",
        lambda: InMemoryChatSessionStore(f":memory:platform-{test_id}:chat"),
    )
    kwargs.setdefault(
        "job_store_factory",
        lambda: InMemoryJobStore(f":memory:platform-{test_id}:jobs"),
    )
    kwargs.setdefault(
        "model_residency_store_factory",
        lambda: InMemoryModelResidencyStore(f":memory:platform-{test_id}:residency"),
    )
    return create_gateway_app(**kwargs)


def test_platform_openapi_covers_contract_hardening_surfaces() -> None:
    client = _client()

    schema = client.get("/openapi.json").json()
    paths = schema["paths"]

    for path in [
        "/api/jobs",
        "/api/providers",
        "/api/providers/refresh",
        "/api/models",
        "/api/models/refresh",
        "/api/model-residency",
        "/api/model-residency/{model_id}",
        "/api/assets",
        "/api/prompts/render",
        "/api/replay/primitives",
        "/api/settings",
        "/api/reports",
        "/api/diagnostics",
    ]:
        assert path in paths


def test_gateway_diagnostics_reads_persisted_model_residency(tmp_path: Path) -> None:
    from app.jobs import ModelResidencyRecord, InMemoryModelResidencyStore

    store = InMemoryModelResidencyStore(tmp_path / "residency-test")
    store.upsert_record(
        ModelResidencyRecord(
            model_id="llm:local-chat",
            model_name="Local Chat",
            provider_id="lmstudio",
            module="chatbot",
            resource_class="gpu:llm",
            status="loaded",
            worker_id="worker:gpu",
            worker_endpoint="http://127.0.0.1:9001",
            estimated_vram_mb=8192,
            compatibility_group="small-local",
        )
    )
    client = TestClient(
        _test_gateway_app(model_residency_store_factory=lambda: store),
        base_url="http://127.0.0.1",
        raise_server_exceptions=False,
        headers={"X-Omnix-Client": "test"},
    )

    diagnostics = client.get("/api/diagnostics").json()

    assert diagnostics["model_residency"]["status"] == "active"
    assert diagnostics["model_residency"]["records"][0]["worker_id"] == "worker:gpu"


def test_gateway_model_residency_report_endpoint_updates_store(tmp_path: Path) -> None:
    from app.jobs import InMemoryModelResidencyStore

    store = InMemoryModelResidencyStore(tmp_path / "residency-test")
    client = TestClient(
        _test_gateway_app(model_residency_store_factory=lambda: store),
        base_url="http://127.0.0.1",
        raise_server_exceptions=False,
        headers={"X-Omnix-Client": "test"},
    )

    report = {
        "model_id": "llm:local-chat",
        "model_name": "Local Chat",
        "provider_id": "lmstudio",
        "module": "chatbot",
        "resource_class": "gpu:llm",
        "status": "loaded",
        "worker_id": "worker:gpu",
        "worker_endpoint": "http://127.0.0.1:9001",
        "estimated_vram_mb": 8192,
        "compatibility_group": "small-local",
    }

    response = client.post("/api/model-residency", json=report)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "active"
    assert payload["records"][0]["model_id"] == "llm:local-chat"
    assert store.list_records()[0].worker_id == "worker:gpu"

    readback = client.get("/api/model-residency")
    assert readback.status_code == 200
    assert readback.json()["records"][0]["estimated_vram_mb"] == 8192

    deleted = client.delete("/api/model-residency/llm:local-chat")
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "idle"
    assert store.list_records() == []


def test_gateway_provider_model_refresh_enqueues_shared_job(tmp_path: Path) -> None:
    from tests.support.in_memory_jobs import InMemoryJobStore

    store = InMemoryJobStore(tmp_path / "jobs-test")
    client = TestClient(
        _test_gateway_app(job_store_factory=lambda: store),
        base_url="http://127.0.0.1",
        raise_server_exceptions=False,
        headers={"X-Omnix-Client": "test"},
    )

    response = client.post("/api/models/refresh", json={"scope": "models", "reason": "test-refresh", "priority": 4})

    assert response.status_code == 200
    payload = response.json()
    assert payload["module"] == "platform"
    assert payload["type"] == "providers.models.refresh"
    assert payload["resource_class"] == "cpu"
    assert payload["priority"] == 4
    assert payload["input_payload"] == {"scope": "models", "reason": "test-refresh"}
    assert [stage["id"] for stage in payload["stages"]] == [
        "discover-providers",
        "discover-local-models",
        "publish-cache-status",
    ]

    events = store.list_events()
    assert events[-1].event_type == "job.created"
    assert events[-1].job_id == payload["id"]


def test_gateway_settings_endpoint_returns_typed_non_secret_summary() -> None:
    response = _client().get("/api/settings")
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "lmstudio"
    assert isinstance(payload["settings"], dict)
    assert "api_key" not in str(payload)


def test_gateway_settings_endpoint_does_not_load_provider_secrets() -> None:
    response = _client().get("/api/settings")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert "secrets" not in payload
    assert "api_keys" not in payload


def test_gateway_settings_endpoint_reports_each_setting_revision() -> None:
    # A client needs the revisions to save: the POST refuses an existing setting without its revision.
    class SavedProviderSettings:
        def get(self, key):
            if key == "provider":
                return {"key": key, "value": "openrouter", "revision": 3}
            return None

        def register_specs(self, _specs):
            return None

    payload = _client(SavedProviderSettings()).get("/api/settings").json()
    assert payload["provider"] == "openrouter"
    assert payload["revisions"]["provider"] == 3
    assert payload["revisions"]["audio_provider_tts"] == 0
    assert set(payload["revisions"]) == set(payload["settings"])


def test_gateway_settings_post_uses_revisioned_typed_patch() -> None:
    from app.settings.service import SettingRevisionConflict

    class FakeSettingsService:
        def __init__(self, conflict: bool = False):
            self.patch_value = None
            self.conflict = conflict

        def get(self, _key):
            return None

        def register_specs(self, _specs):
            return None

        def patch(self, patch_value):
            self.patch_value = patch_value
            if self.conflict:
                raise SettingRevisionConflict("revision conflict")

    service = FakeSettingsService()
    response = _client(service).post(
        "/api/settings",
        json={"values": {"provider": "openrouter"}, "revisions": {"provider": 0}},
    )
    assert response.status_code == 200
    assert response.json() == {"success": True}
    assert service.patch_value.values == {"provider": "openrouter"}
    assert service.patch_value.revisions == {"provider": 0}

    conflict = _client(FakeSettingsService(conflict=True)).post(
        "/api/settings",
        json={"values": {"provider": "openrouter"}, "revisions": {"provider": 0}},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "settings_revision_conflict"


def test_gateway_reports_endpoint_lists_artifacts(tmp_path: Path) -> None:
    from app.observability import reports as reports_module
    report = tmp_path / "run-1" / "report.json"
    report.parent.mkdir(parents=True)
    report.write_text("{}", encoding="utf-8")

    with patch.object(reports_module, "test_results_root", return_value=tmp_path):
        response = _client().get("/api/reports")

    assert response.status_code == 200
    payload = response.json()
    assert payload["reports"][0]["id"] == "run-1/report.json"
    assert payload["reports"][0]["kind"] == "json_report"


def test_gateway_diagnostics_endpoint_reports_worker_summary() -> None:
    from app.providers.cache_status import ProviderModelCachePayload

    with (
        # Sign-in is on by default (WP-4.1); this test reads diagnostics.
        patch.dict("os.environ", {"OMNIX_AUTH_MODE": "disabled"}, clear=True),
        patch(
            "app.composition.gateway.diagnostics.get_provider_model_cache_status",
            return_value=ProviderModelCachePayload(status="ready"),
        ),
    ):
        response = _client().get("/api/diagnostics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["workers"]["status"] == "not_configured"
    assert payload["event_stream"]["transport"] == "sse"
    assert payload["model_residency"]["status"] == "idle"
    assert payload["model_residency"]["policy"]["allow_co_residency"] is False
    assert payload["model_residency"]["records"] == []
    assert payload["provider_model_cache"]["status"] == "ready"
