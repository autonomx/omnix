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


def test_a_service_that_released_an_idle_model_is_started_again(tmp_path, monkeypatch):
    import time

    from app.composition.launcher.service_manager import LauncherServiceManager, ServiceSpec
    from app.runtime.process_control import IDLE_EXIT_CODE

    monkeypatch.setattr("app.composition.launcher.service_manager.initialize_service_token", lambda: "token")
    marker = tmp_path / "ran-once"
    # The first run unloads and exits with the idle code; the second (light) one keeps running until stopped.
    script = (f"import pathlib, sys, time\nmarker = pathlib.Path({str(marker)!r})\n"
              f"if not marker.exists():\n    marker.write_text('1')\n    sys.exit({IDLE_EXIT_CODE})\n"
              "print('light', flush=True)\ntime.sleep(30)\n")
    manager = LauncherServiceManager([
        ServiceSpec(service_id="model", label="Model", command=[sys.executable, "-c", script], cwd=tmp_path),
    ])
    assert manager.start("model")["ok"]
    try:
        for _ in range(500):
            if any(line.endswith("] light") for line in manager._services["model"].logs):  # not the command line
                break
            time.sleep(0.02)
        lines = list(manager._services["model"].logs)
        assert any(f"exited with code {IDLE_EXIT_CODE}" in line for line in lines)
        assert any("starting it again without one" in line for line in lines)
        assert manager._services["model"].status() == "running"
    finally:
        manager.stop("model")


def test_a_service_asked_to_stop_is_not_started_again_by_its_idle_exit(tmp_path, monkeypatch):
    # Review finding (2026-10-31): a stop landing as the service exited for idleness was followed by a restart.
    import time

    from app.composition.launcher.service_manager import LauncherServiceManager, ServiceSpec
    from app.runtime.process_control import IDLE_EXIT_CODE

    monkeypatch.setattr("app.composition.launcher.service_manager.initialize_service_token", lambda: "token")
    script = f"import sys, time\ntime.sleep(0.5)\nsys.exit({IDLE_EXIT_CODE})\n"
    manager = LauncherServiceManager([
        ServiceSpec(service_id="model", label="Model", command=[sys.executable, "-c", script], cwd=tmp_path),
    ])
    assert manager.start("model")["ok"]
    service = manager._services["model"]
    service.stop_requested = True  # stop() as the process exits on its own
    for _ in range(200):
        if any(f"exited with code {IDLE_EXIT_CODE}" in line for line in service.logs):
            break
        time.sleep(0.02)
    time.sleep(0.3)
    assert service.status() != "running"
    assert not any("starting it again" in line for line in service.logs)
