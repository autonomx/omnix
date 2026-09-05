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
