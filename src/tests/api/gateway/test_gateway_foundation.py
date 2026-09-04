"""Contract tests for the thin web gateway foundation."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

SRC_DIR = Path(__file__).resolve().parents[3]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _client() -> TestClient:
    from app.gateway.main import create_gateway_app

    return TestClient(create_gateway_app(), raise_server_exceptions=False)


def test_gateway_health_is_provider_free() -> None:
    client = _client()

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "ok": True,
        "status": "ready",
        "service": "omnix-gateway",
        "format_version": "omnix_gateway_foundation_v1",
    }


def test_gateway_openapi_is_available() -> None:
    client = _client()

    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "Omnix Web Gateway"
    assert "/api/runtime/status" in schema["paths"]
    assert "/api/workers/health" in schema["paths"]
    assert "/api/workers/payload-policy" in schema["paths"]
    assert "/api/compatibility/legacy" in schema["paths"]


def test_gateway_runtime_status_does_not_require_workers() -> None:
    with patch.dict("os.environ", {}, clear=True):
        client = _client()

        response = client.get("/api/runtime/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["status"] == "ready"
    assert payload["gateway"]["service"] == "omnix-gateway"
    assert payload["workers"]["status"] == "not_configured"
    assert payload["workers"]["summary"] == {
        "configured": 0,
        "reachable": 0,
        "unreachable": 0,
        "mocked": 0,
    }
    assert payload["compatibility"]["existing_fastapi_app"] == "run_app:app"


def test_gateway_worker_health_placeholder_is_explicit() -> None:
    with patch.dict("os.environ", {}, clear=True):
        client = _client()

        response = client.get("/api/workers/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["status"] == "not_configured"
    assert payload["workers"] == []
    assert payload["summary"]["configured"] == 0
    assert payload["diagnostics"] == []


def test_gateway_worker_health_uses_mock_mode_for_ci() -> None:
    env = {
        "OMNIX_GATEWAY_MOCK_WORKERS": "1",
        "OMNIX_GATEWAY_MOCK_WORKERS_LIST": "tts,image",
    }
    with patch.dict("os.environ", env, clear=True):
        client = _client()
        response = client.get("/api/workers/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["status"] == "ready"
    assert payload["summary"] == {
        "configured": 2,
        "reachable": 2,
        "unreachable": 0,
        "mocked": 2,
    }
    workers = {worker["id"]: worker for worker in payload["workers"]}
    assert workers["tts"]["mocked"] is True
    assert workers["tts"]["status"] == "ready"
    assert workers["image"]["url"] == "mock://image"


def test_gateway_runtime_status_uses_mock_workers_for_ci_smoke() -> None:
    env = {
        "OMNIX_GATEWAY_MOCK_WORKERS": "1",
        "OMNIX_GATEWAY_MOCK_WORKERS_LIST": "tts,stt,image",
    }
    with patch.dict("os.environ", env, clear=True):
        client = _client()
        response = client.get("/api/runtime/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["status"] == "ready"
    assert payload["workers"]["ok"] is True
    assert payload["workers"]["summary"] == {
        "configured": 3,
        "reachable": 3,
        "unreachable": 0,
        "mocked": 3,
    }
    assert {worker["id"] for worker in payload["workers"]["workers"]} == {"tts", "stt", "image"}
    assert all(worker["mocked"] is True for worker in payload["workers"]["workers"])


def test_gateway_worker_health_reports_unreachable_worker() -> None:
    env = {
        "OMNIX_GATEWAY_WORKERS": "tts",
        "OMNIX_WORKER_TTS_URL": "not-a-url",
    }
    with patch.dict("os.environ", env, clear=True):
        client = _client()
        response = client.get("/api/workers/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["status"] == "degraded"
    assert payload["summary"]["configured"] == 1
    assert payload["summary"]["unreachable"] == 1
    assert payload["workers"][0]["status"] == "unreachable"
    assert payload["diagnostics"][0]["kind"] == "worker_unreachable"


def test_gateway_payload_policy_forbids_browser_worker_access() -> None:
    client = _client()

    response = client.get("/api/workers/payload-policy")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["browser_worker_access"] == "forbidden"
    assert payload["gateway_worker_access"] == "required"
    assert payload["generated_artifacts"] == "return_asset_reference"
    assert payload["base64_media_payloads"] == "transitional_only"


def test_gateway_lifespan_starts_registered_trading_monitor(monkeypatch) -> None:
    from app.gateway import main as gateway_main
    from app.trading import strategy_monitor as monitor_module
    from app.trading.strategy_monitor import TradingStrategyMonitor, register_trading_strategy_monitor

    monkeypatch.setattr(
        gateway_main,
        "recover_abandoned_chat_generation_jobs",
        lambda *_args: 0,
    )
    monkeypatch.setattr(
        monitor_module,
        "managed_finviz_shadow_autoprovision_enabled",
        lambda: False,
    )
    monkeypatch.setattr(
        monitor_module,
        "trading_strategy_monitor_enabled",
        lambda: True,
    )

    async def no_op_run_once(_monitor: TradingStrategyMonitor) -> None:
        return None

    monkeypatch.setattr(TradingStrategyMonitor, "run_once", no_op_run_once)

    app = FastAPI(
        lifespan=lambda current_app: gateway_main._gateway_lifespan(
            current_app,
            get_chat_store=lambda: object(),
            get_job_store=lambda: object(),
        )
    )
    monitor = register_trading_strategy_monitor(app)

    with TestClient(app):
        assert monitor._task is not None
        assert not monitor._task.done()

    assert monitor._task is None


def test_gateway_compatibility_handoff_keeps_legacy_owners_visible() -> None:
    client = _client()

    response = client.get("/api/compatibility/legacy")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["legacy_ui_status"] == "retired"
    assert payload["existing_fastapi_app"] == "run_app:app"
    assert payload["domain_logic_policy"] == "delegate_to_existing_service_modules"
    namespaces = {target["namespace"] for target in payload["handoff_targets"]}
    assert "/api/rpg" in namespaces
    assert "/api/image" in namespaces
    assert "/generated-images" in namespaces
