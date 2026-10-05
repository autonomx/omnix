from __future__ import annotations

from pathlib import Path

from app.launcher.startup import DEFAULT_ENVIRONMENT, apply_launcher_environment

ROOT = Path(__file__).resolve().parents[3]


def test_the_launcher_enables_the_proposal_only_live_agent_pilot(tmp_path) -> None:
    env = apply_launcher_environment(tmp_path, {})

    assert env["HERMES_ENABLED"] == "1"
    assert env["OMNIX_LIVE_AGENT_ENABLED"] == "1"
    assert env["OMNIX_LIVE_AGENT_AUTO_ROUTE_ENABLED"] == "1"
    assert env["OMNIX_LIVE_AGENT_REQUIRE_HERMES"] == "1"
    assert env["OMNIX_START_HERMES"] == "1"
    # Agent debug logs are opt-in (WP-10.1): the launcher does not enable them.
    assert env["OMNIX_AGENT_DEBUG_LOGS"] == "0"
    assert env["OMNIX_LAUNCHER_AUTO_START"] == "1"
    assert env["OMNIX_LAUNCHER_OPEN_BROWSER"] == "1"
    assert ("OMNIX_GATEWAY_STARTUP_TIMEOUT_SECONDS", "420") in DEFAULT_ENVIRONMENT


def test_kasa_requirement_matches_launcher_python_version() -> None:
    gateway_input = (ROOT / "requirements" / "gateway.in").read_text(encoding="utf-8")
    image_input = (ROOT / "requirements" / "image.in").read_text(encoding="utf-8")
    gateway_lock = (ROOT / "requirements" / "gateway.lock.txt").read_text(encoding="utf-8")
    general_requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    setup = (ROOT / "setup.bat").read_text(encoding="utf-8")
    launcher = (ROOT / "src" / "app" / "launcher" / "__main__.py").read_text(encoding="utf-8")

    assert "python-kasa" in gateway_input
    assert "-r gateway.in" in image_input
    assert "-r requirements/gateway.lock.txt" in general_requirements
    assert "python-kasa==" in gateway_lock
    assert "python=3.11" in setup
    assert "--require-hashes -r requirements\\image.lock.txt" in setup
    assert "python-kasa could not be imported" in launcher
    assert "hash-locked image runtime" in launcher


def test_the_windows_credential_flow_stays_in_the_wrapper() -> None:
    batch = (ROOT / "start_all.bat").read_text(encoding="utf-8")
    credential_script = (ROOT / "scripts" / "manage_postgresql_credential.ps1").read_text(encoding="utf-8")

    assert "if not defined OMNIX_DATABASE_URL (" in batch
    assert "manage_postgresql_credential.ps1" in batch and "-Action launch" in batch
    assert 'if /I "%~1"=="--database-credential-injected-check"' in batch
    assert "ConvertFrom-SecureString" in credential_script
    assert "ConvertTo-SecureString" in credential_script
    assert "windows_dpapi_current_user" in credential_script
    assert "[switch]$CheckOnly" in credential_script
    assert "Write-Output $databaseUrl" not in credential_script
