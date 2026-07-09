from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.launcher import control_app as launcher_control_app
from app.launcher import service_manager as launcher_service_manager
from app.launcher.control_app import app
from app.launcher.service_manager import LauncherServiceManager, ServiceSpec, build_default_service_specs, reset_default_manager_for_tests


def test_default_service_specs_keep_image_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_IMAGE_ENABLED", raising=False)
    monkeypatch.delenv("OMNIX_START_IMAGE_SERVICE", raising=False)

    specs = build_default_service_specs(Path("F:/LLM/omnix"))
    by_id = {spec.service_id: spec for spec in specs}

    assert {"stt", "tts", "gateway", "web", "image"}.issubset(by_id)
    assert by_id["image"].enabled is False
    assert by_id["image"].auto_start is False
    assert by_id["image"].optional is True
    assert by_id["gateway"].env["OMNIX_IMAGE_ENABLED"] == "0"
    assert by_id["gateway"].env["OMNIX_IMAGE_URL"] == ""
    assert by_id["gateway"].env["OMNIX_LAUNCHER_KILL_PORT"] == "1"
    expected_tts_model = "F:\\LLM\\omnix\\resources\\models\\tts\\Qwen3-TTS-12Hz-0.6B-Base"
    assert by_id["gateway"].env["OMNIX_TTS_MODEL_DIR"] == expected_tts_model
    assert by_id["gateway"].env["OMNIX_QWEN3_TTS_MODEL_DIR"] == expected_tts_model
    assert by_id["gateway"].ports == (8000,)
    assert by_id["web"].ports == (5173,)
    assert by_id["web"].command[-2:] == ["run", "web:dev"]
    assert by_id["tts"].ports == (5101,)
    assert by_id["stt"].ports == (5201,)
    assert by_id["image"].ports == (5301,)


def test_default_service_specs_image_is_explicit_opt_in(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_IMAGE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_START_IMAGE_SERVICE", "1")

    specs = build_default_service_specs(Path("F:/LLM/omnix"))
    image = {spec.service_id: spec for spec in specs}["image"]

    assert image.enabled is True
    assert image.auto_start is True
    assert image.env["OMNIX_IMAGE_ENABLED"] == "1"
    assert "app.image_service_app:app" in image.command


def test_launcher_dashboard_lists_services_without_starting_processes() -> None:
    manager = LauncherServiceManager([
        ServiceSpec(service_id="fake", label="Fake Service", command=["python", "-V"], cwd=Path("."), description="fake"),
        ServiceSpec(service_id="disabled", label="Disabled", command=["python", "-V"], cwd=Path("."), enabled=False, optional=True),
    ])
    reset_default_manager_for_tests(manager)
    try:
        client = TestClient(app)
        response = client.get("/api/services")
    finally:
        reset_default_manager_for_tests(None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["format_version"] == "omnix_launcher_service_manager_v1"
    services = {item["id"]: item for item in payload["services"]}
    assert services["fake"]["status"] == "stopped"
    assert services["disabled"]["status"] == "disabled"


def test_start_enabled_services_clears_conflicting_ports_before_launch(monkeypatch) -> None:
    cleared_ports: list[int] = []

    class FakeProcess:
        pid = 12345
        stdout: list[str] = []
        returncode = None

        def poll(self) -> None:
            return None

    def fake_popen(*_args, **_kwargs):
        return FakeProcess()

    def fake_kill(port: int) -> list[int]:
        cleared_ports.append(port)
        return [9000 + port]

    monkeypatch.setattr(launcher_service_manager.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(launcher_service_manager, "_kill_processes_for_port", fake_kill)
    monkeypatch.setattr(launcher_service_manager, "_wait_for_port_release", lambda _port: True)

    manager = LauncherServiceManager([
        ServiceSpec(service_id="fake", label="Fake Service", command=["python", "-V"], cwd=Path("."), ports=(5000, 5101)),
    ])

    result = manager.start_auto_services()

    assert result["started"]["fake"]["ok"] is True
    assert cleared_ports == [5000, 5101]
    logs = manager.logs("fake")
    assert any("stopped conflicting process(es) on port 5000" in line for line in logs)
    assert any("stopped conflicting process(es) on port 5101" in line for line in logs)


def test_launcher_dashboard_html_uses_safe_script_and_event_handlers() -> None:
    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    text = response.text
    assert "join('\\n')" in text
    assert "join('\n')" not in text
    assert "onclick=" not in text
    assert "id=\"start-auto\"" in text
    assert "id=\"open-app-private\"" in text
    assert "id=\"stop-all\"" in text
    assert "addEventListener('click'" in text
    assert "addEventListener('click', openAppPrivate)" in text
    assert "data-service-id=" in text
    assert "data-action=\"start\"" in text


def test_launcher_dashboard_html_exposes_copy_logs_buttons() -> None:
    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    text = response.text
    assert "Copy logs" in text
    assert "data-action=\"copy-logs\"" in text
    assert "copyLogs(serviceId" in text
    assert "navigator.clipboard.writeText" in text
    assert "document.execCommand('copy')" in text
    assert "logs?limit=500" in text
    assert "# Omnix launcher logs:" in text


def test_launcher_dashboard_favicon_is_no_content() -> None:
    client = TestClient(app)
    response = client.get("/favicon.ico")

    assert response.status_code == 204


def test_launcher_dashboard_logs_endpoint_returns_text_for_known_service() -> None:
    manager = LauncherServiceManager([
        ServiceSpec(service_id="fake", label="Fake Service", command=["python", "-V"], cwd=Path("."), description="fake"),
    ])
    reset_default_manager_for_tests(manager)
    try:
        manager._services["fake"].logs.extend(["line one", "line two"])
        client = TestClient(app)
        response = client.get("/api/services/fake/logs?limit=10")
    finally:
        reset_default_manager_for_tests(None)

    assert response.status_code == 200
    assert response.text == "line one\nline two"


def test_launcher_dashboard_rejects_unknown_service() -> None:
    manager = LauncherServiceManager([])
    reset_default_manager_for_tests(manager)
    try:
        client = TestClient(app)
        response = client.post("/api/services/missing/start")
    finally:
        reset_default_manager_for_tests(None)

    assert response.status_code == 404


def test_launcher_dashboard_private_app_button_opens_private_browser(monkeypatch) -> None:
    launched: list[list[str]] = []

    monkeypatch.setenv("OMNIX_APP_OPEN_URL", "http://localhost:500/")
    monkeypatch.delenv("OMNIX_PRIVATE_BROWSER", raising=False)
    monkeypatch.delenv("OMNIX_BROWSER_EXE", raising=False)
    monkeypatch.setattr(
        launcher_control_app.shutil,
        "which",
        lambda name: "C:/Browser/msedge.exe" if name in {"msedge", "msedge.exe"} else None,
    )
    monkeypatch.setattr(launcher_control_app.Path, "exists", lambda _self: False)

    def fake_popen(command, **_kwargs):
        launched.append(command)

        class FakeProcess:
            pid = 12345

        return FakeProcess()

    monkeypatch.setattr(launcher_control_app.subprocess, "Popen", fake_popen)

    client = TestClient(app)
    response = client.post("/api/open-app-private")

    assert response.status_code == 200
    assert response.json()["url"] == "http://localhost:500/"
    assert launched == [["C:/Browser/msedge.exe", "--new-window", "--inprivate", "http://localhost:500/"]]


def test_start_all_routes_through_launcher_dashboard() -> None:
    text = Path("start_all.bat").read_text(encoding="utf-8")

    assert "app.launcher.control_app:app" in text
    assert "--port 5055" in text
    assert "Launcher Control" in text
    assert "OMNIX_APP_OPEN_URL" in text
    assert "http://localhost:5173/" in text
    assert "http://localhost:5000/" not in text
    assert 'start "Parakeet STT"' not in text
    assert 'start "Omnix TTS"' not in text
    assert 'start "Omnix FastAPI"' not in text
    assert 'start "Omnix Image Service"' not in text
