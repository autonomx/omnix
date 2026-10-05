"""``python -m app.composition.launcher start`` migrates first, then starts the gateway and the web app (WP-11.4)."""
from __future__ import annotations

import argparse
import sys

import httpx

from app.composition.launcher import __main__ as launcher


def _client(gateway_ready_after: int, calls: list[str]) -> httpx.Client:
    health_checks = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        if request.url.path == "/api/health":
            health_checks["count"] += 1
            return httpx.Response(200 if health_checks["count"] > gateway_ready_after else 503)
        if request.url.path == "/api/services/web/start":
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(200, json={"ok": True, "services": []})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_the_gateway_starts_once_and_the_web_app_after_it_is_healthy():
    calls: list[str] = []
    ready = launcher.start_services(
        "http://launcher", "http://gateway", timeout_seconds=30,
        client=_client(gateway_ready_after=2, calls=calls), sleep=lambda _seconds: None,
    )
    assert ready
    assert calls.count("POST /api/services/gateway/start") == 1
    assert calls.index("POST /api/services/gateway/start") < calls.index("POST /api/services/web/start")
    assert calls[-1] == "POST /api/services/web/start"


def test_start_stops_when_migrations_fail(monkeypatch):
    steps: list[tuple[str, ...]] = []

    def fake_module(*args: str) -> int:
        steps.append(args)
        return 1 if args[-1] == "migrate" else 0

    from app.composition.launcher import startup

    monkeypatch.setattr(launcher, "_module", fake_module)
    monkeypatch.setattr(sys, "version_info", (3, 11, 0))
    monkeypatch.setattr(startup, "launcher_already_running", lambda _port=5055: False)
    monkeypatch.setattr(startup, "interpreter_problems", lambda _config: ([], []))
    monkeypatch.setattr(startup, "apply_launcher_environment", lambda _root: {})
    result = launcher.start(argparse.Namespace(
        gateway_url="http://gateway", startup_timeout=1, postgres_container=None, postgres_only=False, check=False,
    ))
    assert result == 1
    assert steps == [("app.persistence", "health"), ("app.persistence", "migrate")]


def test_a_missing_executable_is_a_failed_start_not_a_launcher_error(tmp_path, monkeypatch):
    from app.composition.launcher.service_manager import LauncherServiceManager, ServiceSpec

    monkeypatch.setattr("app.composition.launcher.service_manager.initialize_service_token", lambda: "token")
    manager = LauncherServiceManager([
        ServiceSpec(service_id="tool", label="Tool", command=[str(tmp_path / "missing-binary")], cwd=tmp_path),
    ])
    result = manager.start("tool")
    assert result["ok"] is False
    assert result["error"] == "executable_unavailable"
    assert any("could not start" in line for line in result["service"]["recent_logs"])
