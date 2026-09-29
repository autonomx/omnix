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
    assert 'if not defined OMNIX_AGENT_DEBUG_LOGS set "OMNIX_AGENT_DEBUG_LOGS=1"' in source
    assert (
        'if not defined OMNIX_AGENT_LOG_DIR '
        'set "OMNIX_AGENT_LOG_DIR=%~dp0resources\\logs\\agent"'
    ) in source
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


def test_windows_launcher_loads_protected_database_credential_and_checks_health() -> None:
    root = Path(__file__).resolve().parents[3]
    source = (root / "start_all.bat").read_text(encoding="utf-8")
    credential_script = (root / "scripts" / "manage_postgresql_credential.ps1").read_text(
        encoding="utf-8"
    )

    assert 'if not defined OMNIX_DATABASE_URL (' in source
    assert "manage_postgresql_credential.ps1" in source
    assert "-Action launch" in source
    assert 'set "OMNIX_LAUNCHER_AUTO_START=1"' in source
    assert 'set "OMNIX_LAUNCHER_OPEN_BROWSER=1"' in source
    assert 'if not defined OMNIX_BLOB_ROOT' in source
    assert r"..\omnix-runtime\blobs" in source
    assert '"%RPG_FLUX_PYTHON%" -m app.persistence health' in source
    assert 'if /I "%~1"=="--database-credential-injected-check"' in source
    assert "ConvertFrom-SecureString" in credential_script
    assert "ConvertTo-SecureString" in credential_script
    assert "windows_dpapi_current_user" in credential_script
    assert "POSTGRES_PASSWORD" in credential_script
    assert "[switch]$CheckOnly" in credential_script
    assert "Write-Output $databaseUrl" not in credential_script


def test_windows_launcher_runs_migrations_after_database_checks_before_services() -> None:
    root = Path(__file__).resolve().parents[3]
    source = (root / "start_all.bat").read_text(encoding="utf-8")

    health_check = source.index('"%RPG_FLUX_PYTHON%" -m app.persistence health')
    credential_check = source.index('if /I "%~1"=="--database-credential-injected-check"')
    migration = source.index('"%RPG_FLUX_PYTHON%" -m app.persistence migrate')
    launcher_start = source.index('"%RPG_FLUX_PYTHON%" -m uvicorn app.launcher.runtime_control_app:app')

    assert health_check < credential_check < migration < launcher_start
    assert "PostgreSQL migrations failed. Omnix services were not started." in source


def test_windows_launcher_retries_web_after_slow_gateway_startup() -> None:
    root = Path(__file__).resolve().parents[3]
    source = (root / "start_all.bat").read_text(encoding="utf-8")

    assert (
        'if not defined OMNIX_GATEWAY_STARTUP_TIMEOUT_SECONDS '
        'set "OMNIX_GATEWAY_STARTUP_TIMEOUT_SECONDS=420"'
    ) in source
    assert "/api/services/web/start" in source
    assert "$webUrl='http://127.0.0.1:5173/'" in source
    assert "Invoke-WebRequest -UseBasicParsing -Uri $webUrl" in source
    assert "Omnix gateway and web app are ready." in source


def test_kasa_requirement_matches_launcher_python_version() -> None:
    root = Path(__file__).resolve().parents[3]
    gateway_input = (root / "requirements" / "gateway.in").read_text(encoding="utf-8")
    image_input = (root / "requirements" / "image.in").read_text(encoding="utf-8")
    gateway_lock = (root / "requirements" / "gateway.lock.txt").read_text(encoding="utf-8")
    general_requirements = (root / "requirements.txt").read_text(encoding="utf-8")
    setup = (root / "setup.bat").read_text(encoding="utf-8")
    launcher = (root / "start_all.bat").read_text(encoding="utf-8")

    assert "python-kasa" in gateway_input
    assert "-r gateway.in" in image_input
    assert "-r requirements/gateway.lock.txt" in general_requirements
    assert "python-kasa==" in gateway_lock
    assert "python=3.11" in setup
    assert "--require-hashes -r requirements\\image.lock.txt" in setup
    assert "Run setup.bat to install the hash-locked image runtime" in launcher
    assert "python-kasa^>=0.7.7" not in launcher
    assert "python-kasa could not be imported" in launcher


def test_windows_launcher_rejects_duplicate_before_starting_services() -> None:
    root = Path(__file__).resolve().parents[3]
    source = (root / "start_all.bat").read_text(encoding="utf-8")

    assert "Launcher already listening on http://127.0.0.1:5055" in source
    assert source.index("Launcher already listening") < source.index('start "Omnix Startup Check"')
