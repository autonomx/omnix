"""Representative platform contract tests for settings, reports, and diagnostics."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


SRC_DIR = Path(__file__).resolve().parents[3]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _client() -> TestClient:
    from app.gateway.main import create_gateway_app

    return TestClient(create_gateway_app(), raise_server_exceptions=False)


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
    from app.gateway.main import create_gateway_app
    from app.jobs import ModelResidencyRecord, SQLiteModelResidencyStore

    store = SQLiteModelResidencyStore(tmp_path / "residency.sqlite")
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
        create_gateway_app(model_residency_store_factory=lambda: store),
        raise_server_exceptions=False,
    )

    diagnostics = client.get("/api/diagnostics").json()

    assert diagnostics["model_residency"]["status"] == "active"
    assert diagnostics["model_residency"]["records"][0]["worker_id"] == "worker:gpu"


def test_gateway_model_residency_report_endpoint_updates_store(tmp_path: Path) -> None:
    from app.gateway.main import create_gateway_app
    from app.jobs import SQLiteModelResidencyStore

    store = SQLiteModelResidencyStore(tmp_path / "residency.sqlite")
    client = TestClient(
        create_gateway_app(model_residency_store_factory=lambda: store),
        raise_server_exceptions=False,
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
    from app.gateway.main import create_gateway_app
    from app.jobs import SQLiteJobStore

    store = SQLiteJobStore(tmp_path / "jobs.sqlite")
    client = TestClient(create_gateway_app(job_store_factory=lambda: store), raise_server_exceptions=False)

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


def test_gateway_settings_endpoint_returns_sanitized_summary() -> None:
    with patch(
        "app.shared.load_settings",
        return_value={
            "provider": "lmstudio",
            "audio_provider_tts": "faster-qwen3-tts",
            "audio_provider_stt": "parakeet",
            "openrouter": {"api_key": "secret"},
            "image": {"enabled": True},
            "rpg_visual": {"enabled": False},
        },
    ):
        response = _client().get("/api/settings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "lmstudio"
    assert payload["image_enabled"] is True
    assert "api_key" not in payload
    assert "openrouter" not in payload


def test_gateway_settings_endpoint_keeps_legacy_success_envelope_with_masked_keys() -> None:
    with (
        patch(
            "app.shared.load_settings",
            return_value={
                "provider": "openrouter",
                "openrouter": {"model": "openai/gpt-4o-mini"},
                "cerebras": {"api_key": "abc"},
                "image": {"enabled": False},
                "rpg_visual": {"enabled": True},
            },
        ),
        patch("app.shared.load_secrets", return_value={"api_keys": {"openrouter": "sk-live-secret"}}),
    ):
        response = _client().get("/api/settings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["settings"]["provider"] == "openrouter"
    assert payload["settings"]["openrouter"]["api_key"] == "***cret"
    assert payload["settings"]["cerebras"]["api_key"] == "****"


def test_gateway_settings_post_preserves_legacy_mutation_semantics() -> None:
    saved_settings = {}
    saved_secrets = {}

    with (
        patch(
            "app.shared.load_settings",
            return_value={
                "provider": "lmstudio",
                "lmstudio": {"base_url": "http://localhost:1234"},
                "openrouter": {"model": "old"},
                "cerebras": {},
                "llamacpp": {},
            },
        ),
        patch("app.shared.load_secrets", return_value={"api_keys": {}}),
        patch("app.shared.save_settings", side_effect=lambda settings: saved_settings.update(settings)),
        patch("app.shared.save_secrets", side_effect=lambda secrets: saved_secrets.update(secrets)),
    ):
        response = _client().post(
            "/api/settings",
            json={
                "provider": "openrouter",
                "openrouter": {"api_key": "sk-new-key", "model": "openai/gpt-4o-mini"},
                "lmstudio": {"base_url": "http://localhost:5678"},
            },
        )

    assert response.status_code == 200
    assert response.json() == {"success": True}
    assert saved_settings["provider"] == "openrouter"
    assert saved_settings["openrouter"]["model"] == "openai/gpt-4o-mini"
    assert "api_key" not in saved_settings["openrouter"]
    assert saved_settings["lmstudio"]["base_url"] == "http://localhost:5678"
    assert saved_secrets["api_keys"]["openrouter"] == "sk-new-key"


def test_gateway_reports_endpoint_lists_artifacts(tmp_path: Path) -> None:
    from app.platform import reports as reports_module

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
        patch.dict("os.environ", {}, clear=True),
        patch(
            "app.platform.diagnostics.get_provider_model_cache_status",
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
