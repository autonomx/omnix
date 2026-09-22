from __future__ import annotations

from pathlib import Path

from app.launcher import service_manager as launcher_service_manager
from app.launcher.service_manager import (
    LauncherServiceManager,
    ServiceSpec,
    build_default_service_specs,
)


def test_image_service_can_be_started_manually_without_auto_start(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_IMAGE_ENABLED", "1")
    monkeypatch.delenv("OMNIX_START_IMAGE_SERVICE", raising=False)
    monkeypatch.delenv("OMNIX_IMAGE_PRELOAD", raising=False)
    monkeypatch.delenv("OMNIX_IMAGE_WARMUP", raising=False)

    specs = build_default_service_specs(Path("F:/LLM/omnix"))
    by_id = {spec.service_id: spec for spec in specs}
    image = by_id["image"]

    assert image.enabled is True
    assert image.auto_start is False
    assert image.env["OMNIX_IMAGE_PRELOAD"] == "0"
    assert image.env["OMNIX_IMAGE_WARMUP"] == "0"
    assert by_id["gateway"].env["OMNIX_IMAGE_URL"] == "http://127.0.0.1:5301"


def test_image_service_auto_start_remains_explicit(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_IMAGE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_START_IMAGE_SERVICE", "1")

    specs = build_default_service_specs(Path("F:/LLM/omnix"))
    image = {spec.service_id: spec for spec in specs}["image"]

    assert image.enabled is True
    assert image.auto_start is True


def test_gateway_defaults_agent_repository_to_launcher_checkout(monkeypatch) -> None:
    root = Path("F:/LLM/omnix")
    monkeypatch.delenv("OMNIX_AGENT_DEFAULT_REPOSITORY", raising=False)

    specs = build_default_service_specs(root)
    gateway = {spec.service_id: spec for spec in specs}["gateway"]

    assert gateway.env["OMNIX_AGENT_DEFAULT_REPOSITORY"] == str(root)


def test_gateway_defaults_agent_debug_logging_to_resources_logs(monkeypatch) -> None:
    root = Path("F:/LLM/omnix")
    monkeypatch.delenv("OMNIX_AGENT_DEBUG_LOGS", raising=False)
    monkeypatch.delenv("OMNIX_AGENT_LOG_DIR", raising=False)
    monkeypatch.delenv("OMNIX_AGENT_LOG_RETENTION_DAYS", raising=False)
    monkeypatch.delenv("OMNIX_AGENT_LOG_MAX_FIELD_CHARS", raising=False)
    monkeypatch.delenv("OMNIX_AGENT_BROWSER_BACKEND", raising=False)

    specs = build_default_service_specs(root)
    gateway = {spec.service_id: spec for spec in specs}["gateway"]

    assert gateway.env["OMNIX_AGENT_DEBUG_LOGS"] == "0"
    assert gateway.env["OMNIX_AGENT_LOG_DIR"] == str(
        root / "resources" / "logs" / "agent"
    )
    assert gateway.env["OMNIX_AGENT_LOG_RETENTION_DAYS"] == "30"
    assert gateway.env["OMNIX_AGENT_LOG_MAX_FIELD_CHARS"] == "12000"
    expected_browser_backend = "playwright" if launcher_service_manager.os.name == "nt" else "agent-browser"
    assert gateway.env["OMNIX_AGENT_BROWSER_BACKEND"] == expected_browser_backend


def test_gateway_preserves_agent_debug_logging_overrides(monkeypatch) -> None:
    root = Path("F:/LLM/omnix")
    monkeypatch.setenv("OMNIX_AGENT_DEBUG_LOGS", "1")
    monkeypatch.setenv("OMNIX_AGENT_LOG_DIR", "D:/omnix-agent-logs")
    monkeypatch.setenv("OMNIX_AGENT_LOG_RETENTION_DAYS", "7")
    monkeypatch.setenv("OMNIX_AGENT_LOG_MAX_FIELD_CHARS", "2048")

    specs = build_default_service_specs(root)
    gateway = {spec.service_id: spec for spec in specs}["gateway"]

    assert gateway.env["OMNIX_AGENT_DEBUG_LOGS"] == "1"
    assert gateway.env["OMNIX_AGENT_LOG_DIR"] == "D:/omnix-agent-logs"
    assert gateway.env["OMNIX_AGENT_LOG_RETENTION_DAYS"] == "7"
    assert gateway.env["OMNIX_AGENT_LOG_MAX_FIELD_CHARS"] == "2048"


def test_gateway_preserves_browser_backend_override(monkeypatch) -> None:
    root = Path("F:/LLM/omnix")
    monkeypatch.setenv("OMNIX_AGENT_BROWSER_BACKEND", "agent-browser")

    specs = build_default_service_specs(root)
    gateway = {spec.service_id: spec for spec in specs}["gateway"]

    assert gateway.env["OMNIX_AGENT_BROWSER_BACKEND"] == "agent-browser"


def test_gateway_preserves_explicit_agent_repository_override(monkeypatch) -> None:
    root = Path("F:/LLM/omnix")
    override = "D:/work/other-project"
    monkeypatch.setenv("OMNIX_AGENT_DEFAULT_REPOSITORY", override)

    specs = build_default_service_specs(root)
    gateway = {spec.service_id: spec for spec in specs}["gateway"]

    assert gateway.env["OMNIX_AGENT_DEFAULT_REPOSITORY"] == override


def test_launcher_drops_retired_semantic_shadow_environment(monkeypatch, tmp_path) -> None:
    captured_environment: dict[str, str] = {}

    class FakeProcess:
        pid = 12345
        stdout: list[str] = []
        returncode = None

        def poll(self):
            return None

    def fake_popen(*_args, **kwargs):
        captured_environment.update(kwargs["env"])
        return FakeProcess()

    monkeypatch.setenv("OMNIX_AGENT_SEMANTIC_ROUTING_MODE", "shadow")
    monkeypatch.setattr(launcher_service_manager.subprocess, "Popen", fake_popen)
    manager = LauncherServiceManager([
        ServiceSpec(
            service_id="gateway",
            label="Gateway",
            command=["python", "-V"],
            cwd=tmp_path,
        )
    ])

    result = manager.start("gateway")

    assert result["ok"] is True
    assert "OMNIX_AGENT_SEMANTIC_ROUTING_MODE" not in captured_environment


def test_auto_start_waits_for_gateway_before_starting_web(monkeypatch, tmp_path) -> None:
    events: list[str] = []
    monkeypatch.setenv("OMNIX_GATEWAY_STARTUP_TIMEOUT_SECONDS", "75")
    manager = LauncherServiceManager([
        ServiceSpec(
            service_id="gateway",
            label="Gateway",
            command=["python", "-V"],
            cwd=tmp_path,
            ports=(8000,),
        ),
        ServiceSpec(
            service_id="web",
            label="Web",
            command=["npm", "run", "dev"],
            cwd=tmp_path,
            ports=(5173,),
        ),
    ])

    monkeypatch.setattr(manager, "start", lambda service_id: events.append(service_id) or {"ok": True})
    monkeypatch.setattr(
        launcher_service_manager,
        "_wait_for_port_open",
        lambda port, *, timeout_s: events.append(f"ready:{port}:{timeout_s:g}") or True,
    )

    result = manager.start_auto_services()

    assert events == ["gateway", "ready:8000:75", "web"]
    assert result["started"]["gateway"]["ready"] is True


def test_auto_start_retries_slow_gateway_before_starting_web(monkeypatch, tmp_path) -> None:
    started_commands: list[list[str]] = []
    readiness_timeouts: list[float] = []
    readiness_results = iter([False, True])

    class FakeProcess:
        pid = 12345
        stdout: list[str] = []
        returncode = None

        def poll(self):
            return None

    def fake_popen(command, **_kwargs):
        started_commands.append(command)
        return FakeProcess()

    def fake_wait(_port: int, *, timeout_s: float) -> bool:
        readiness_timeouts.append(timeout_s)
        return next(readiness_results)

    monkeypatch.setenv("OMNIX_GATEWAY_STARTUP_TIMEOUT_SECONDS", "90")
    monkeypatch.setattr(launcher_service_manager.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(launcher_service_manager, "_wait_for_port_open", fake_wait)
    monkeypatch.setattr(launcher_service_manager, "_kill_processes_for_port", lambda _port: [])
    manager = LauncherServiceManager([
        ServiceSpec(
            service_id="gateway",
            label="Gateway",
            command=["python", "gateway.py"],
            cwd=tmp_path,
            ports=(8000,),
        ),
        ServiceSpec(
            service_id="web",
            label="Web",
            command=["npm", "run", "dev"],
            cwd=tmp_path,
            ports=(5173,),
        ),
    ])

    result = manager.start_auto_services()

    assert result["started"]["gateway"]["ready"] is False
    assert result["started"]["web"]["ok"] is True
    assert readiness_timeouts == [90.0, 90.0]
    assert started_commands == [["python", "gateway.py"], ["npm", "run", "dev"]]
    assert any("web startup will retry readiness" in line for line in manager.logs("gateway"))


def test_gateway_ready_timeout_rejects_invalid_overrides(monkeypatch) -> None:
    for value in ("", "not-a-number", "0", "-1", "nan", "inf"):
        monkeypatch.setenv("OMNIX_GATEWAY_STARTUP_TIMEOUT_SECONDS", value)
        assert (
            launcher_service_manager._gateway_ready_timeout_seconds()
            == launcher_service_manager.DEFAULT_GATEWAY_READY_TIMEOUT_SECONDS
        )


def test_starting_web_requires_gateway_readiness(monkeypatch, tmp_path) -> None:
    manager = LauncherServiceManager([
        ServiceSpec(
            service_id="gateway",
            label="Gateway",
            command=["python", "-V"],
            cwd=tmp_path,
            ports=(8000,),
        ),
        ServiceSpec(
            service_id="web",
            label="Web",
            command=["npm", "run", "dev"],
            cwd=tmp_path,
            ports=(5173,),
        ),
    ])
    monkeypatch.setattr(
        manager,
        "_ensure_gateway_ready",
        lambda: (False, {"ok": False, "error": "gateway_not_ready"}),
    )

    def fail_popen(*_args, **_kwargs):
        raise AssertionError("web must not start")

    monkeypatch.setattr(
        launcher_service_manager.subprocess,
        "Popen",
        fail_popen,
    )

    result = manager.start("web")

    assert result["ok"] is False
    assert result["error"] == "gateway_not_ready"
    assert result["gateway"]["error"] == "gateway_not_ready"
