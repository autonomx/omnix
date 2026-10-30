"""The launcher starts the live portrait service when its environment exists (roadmap Phase 1)."""
from __future__ import annotations

from pathlib import Path

from app.composition.launcher.runtime_control_app import build_runtime_service_specs


def test_the_portrait_service_is_optional_and_starts_only_with_its_environment(monkeypatch, tmp_path: Path) -> None:
    python = tmp_path / "python.exe"
    monkeypatch.setenv("OMNIX_PORTRAIT_PYTHON", str(python))
    monkeypatch.delenv("OMNIX_PORTRAIT_ENABLED", raising=False)
    monkeypatch.delenv("OMNIX_PORTRAIT_URL", raising=False)

    portrait = {spec.service_id: spec for spec in build_runtime_service_specs()}["portrait"]
    assert portrait.optional and not portrait.startup_critical and portrait.ports == (5501,)
    assert portrait.command == [str(python), "-m", "services.portrait.portrait_server"]
    assert portrait.enabled and not portrait.auto_start  # no environment yet
    assert portrait.env["OMNIX_PORTRAIT_URL"] == "http://127.0.0.1:5501"

    python.write_text("")
    assert {spec.service_id: spec for spec in build_runtime_service_specs()}["portrait"].auto_start


def test_the_portrait_service_can_be_switched_off(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_PORTRAIT_ENABLED", "0")
    specs = {spec.service_id: spec for spec in build_runtime_service_specs()}
    assert not specs["portrait"].enabled and not specs["portrait"].auto_start
    assert specs["gateway"].env["OMNIX_PORTRAIT_URL"] == ""
