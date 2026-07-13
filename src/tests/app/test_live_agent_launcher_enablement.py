from __future__ import annotations

from pathlib import Path


def test_windows_launcher_enables_proposal_only_live_agent_pilot() -> None:
    root = Path(__file__).resolve().parents[3]
    source = (root / "start_all.bat").read_text(encoding="utf-8")

    assert 'if not defined HERMES_ENABLED set "HERMES_ENABLED=1"' in source
    assert 'if not defined OMNIX_LIVE_AGENT_ENABLED set "OMNIX_LIVE_AGENT_ENABLED=1"' in source
    assert (
        'if not defined OMNIX_LIVE_AGENT_AUTO_ROUTE_ENABLED '
        'set "OMNIX_LIVE_AGENT_AUTO_ROUTE_ENABLED=1"'
    ) in source
    assert (
        'if not defined OMNIX_LIVE_AGENT_REQUIRE_HERMES '
        'set "OMNIX_LIVE_AGENT_REQUIRE_HERMES=1"'
    ) in source
    assert 'if not defined OMNIX_START_HERMES set "OMNIX_START_HERMES=1"' in source
    assert 'start "Omnix Hermes"' not in source
    assert "app.launcher.runtime_control_app:app" in source


def test_windows_launcher_starts_existing_postgres_container_and_waits_for_health() -> None:
    root = Path(__file__).resolve().parents[3]
    source = (root / "start_all.bat").read_text(encoding="utf-8")

    assert 'set "OMNIX_POSTGRES_CONTAINER=omnix-postgres"' in source
    assert "call :ensure_postgres" in source
    assert 'if /I "%~1"=="--postgres-only"' in source
    assert 'docker start "%OMNIX_POSTGRES_CONTAINER%"' in source
    assert '{{.State.Health.Status}}' in source
    assert "docker compose" not in source
    assert "Provision it with docker-compose.postgres.yml" in source
