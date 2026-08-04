from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

import kyutai_stt_runtime
from app.launcher import kyutai_readiness_control as readiness
from app.launcher import runtime_control_app


class _FakeManager:
    def __init__(self, *, moshi: str = "running", adapter: str = "running") -> None:
        self.statuses = {"kyutai_moshi": moshi, "kyutai_stt": adapter}
        self.restarted: list[str] = []

    def service_snapshot(self, service_id: str):
        status = self.statuses[service_id]
        return {
            "id": service_id,
            "status": status,
            "enabled": True,
            "pid": 100 if status == "running" else None,
            "uptime_seconds": 12.0,
            "last_returncode": None,
        }

    def restart(self, service_id: str):
        self.restarted.append(service_id)
        self.statuses[service_id] = "running"
        return {"ok": True, "service_id": service_id}


def _ready_health() -> dict[str, object]:
    return {
        "ok": True,
        "provider": "kyutai",
        "state": "closed",
        "upstream_ready": True,
        "last_ready_at": 1_000.0,
        "last_error": None,
        "last_error_code": None,
        "last_error_type": None,
        "last_error_stage": None,
        "failures_in_window": 0,
        "attempts_in_window": 1,
        "retry_after_seconds": 0.0,
        "sample_rate": 24_000,
        "frame_samples": 1_920,
    }


def _ready_authority() -> dict[str, object]:
    return {
        "ok": True,
        "provider": "kyutai",
        "mode": "test",
        "eligible": True,
        "upstream_ready": True,
        "model_warm": True,
        "language_supported": True,
        "quality_gate_passed": False,
        "contention_gate_passed": False,
        "reasons": [],
    }


def test_runtime_launcher_html_exposes_kyutai_readiness_controls() -> None:
    response = TestClient(runtime_control_app.app).get("/")

    assert response.status_code == 200
    text = response.text
    assert 'id="kyutai-readiness-panel"' in text
    assert 'id="probe-kyutai"' in text
    assert 'id="restart-kyutai"' in text
    assert 'id="copy-kyutai-diagnostics"' in text
    assert "/api/launcher/kyutai-readiness/probe" in text
    assert 'id="hf-token-panel"' in text
    assert "refreshHuggingFaceTokenStatus();" in text
    assert "refreshKyutaiReadiness(false);" in text


def test_readiness_endpoint_reports_ready_without_exposing_raw_error(
    monkeypatch,
) -> None:
    manager = _FakeManager()
    calls: list[tuple[str, dict[str, str] | None]] = []

    def fake_fetch(path: str, *, query=None):
        calls.append((path, query))
        return _ready_health() if path == "/healthz" else _ready_authority()

    monkeypatch.setattr(readiness, "get_default_manager", lambda: manager)
    monkeypatch.setattr(readiness, "_fetch_adapter_json", fake_fetch)

    response = TestClient(runtime_control_app.app).get(
        "/api/launcher/kyutai-readiness"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "ready"
    assert payload["authority"]["eligible"] is True
    assert payload["health"]["upstream_ready"] is True
    assert "last_error" not in payload["health"]
    assert calls == [
        ("/healthz", None),
        ("/authorityz", {"language": "en", "mode": "test"}),
    ]


def test_forced_probe_surfaces_safe_connection_closed_diagnostic(
    monkeypatch,
) -> None:
    manager = _FakeManager()
    calls: list[tuple[str, dict[str, str] | None]] = []

    def fake_fetch(path: str, *, query=None):
        calls.append((path, query))
        if path == "/healthz":
            return {
                **_ready_health(),
                "ok": False,
                "upstream_ready": False,
                "last_ready_at": None,
                "last_error": "private local transport detail",
                "last_error_code": "upstream_connection_closed",
                "last_error_type": "ConnectionClosedError",
                "last_error_stage": "ready",
            }
        return {
            **_ready_authority(),
            "ok": False,
            "eligible": False,
            "upstream_ready": False,
            "model_warm": False,
            "reasons": [
                "upstream_not_ready",
                "upstream_connection_closed",
                "model_not_warm",
            ],
        }

    monkeypatch.setattr(readiness, "get_default_manager", lambda: manager)
    monkeypatch.setattr(readiness, "_fetch_adapter_json", fake_fetch)

    response = TestClient(runtime_control_app.app).post(
        "/api/launcher/kyutai-readiness/probe"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "blocked"
    assert payload["failure_code"] == "upstream_connection_closed"
    assert "closed it before" in payload["message"]
    assert payload["health"]["last_error_type"] == "ConnectionClosedError"
    assert "private local transport detail" not in response.text
    assert calls[0] == ("/healthz", {"force": "true"})


def test_restart_endpoint_restarts_moshi_before_adapter(monkeypatch) -> None:
    manager = _FakeManager(moshi="stopped", adapter="stopped")
    monkeypatch.setattr(readiness, "get_default_manager", lambda: manager)

    response = TestClient(runtime_control_app.app).post(
        "/api/launcher/kyutai-readiness/restart"
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert manager.restarted == ["kyutai_moshi", "kyutai_stt"]


def test_runtime_forced_health_probe_bypasses_probe_cache(monkeypatch) -> None:
    observed: list[float] = []

    async def fake_http_ready() -> tuple[bool, str | None, str | None]:
        return True, None, None

    async def fake_probe(*, language: str, max_age_seconds: float) -> bool:
        assert language == "en"
        observed.append(max_age_seconds)
        return True

    async def fake_health():
        return {
            "provider": "kyutai",
            "state": "closed",
            "upstream_ready": True,
        }

    monkeypatch.setattr(kyutai_stt_runtime, "_moshi_http_ready", fake_http_ready)
    monkeypatch.setattr(kyutai_stt_runtime.provider, "probe", fake_probe)
    monkeypatch.setattr(kyutai_stt_runtime.provider, "health", fake_health)

    payload = asyncio.run(kyutai_stt_runtime._probed_health("en", force=True))

    assert payload["ok"] is True
    assert payload["http_ready"] is True
    assert observed == [0.0]
