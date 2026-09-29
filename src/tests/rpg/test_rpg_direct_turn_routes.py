from __future__ import annotations
from tests.support.routers import include_router_registrar

import os
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.rpg.api.feature_routes.rpg_session_routes import register_rpg_session_routes
from app.rpg.jobs.turn_job_mirror import install_rpg_turn_job_mirror_hook


def test_gateway_fresh_start_installs_required_rpg_turn_hooks() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo_root / "src")
    script = """
from app.gateway.main import create_gateway_app
app = create_gateway_app()
from app.rpg.session import interactive_first_call_runtime as runtime
assert getattr(runtime, '_omnix_interaction_timeline_hook_installed', False)
assert getattr(runtime, '_omnix_interaction_lifecycle_runtime_hook_installed', False)
assert getattr(runtime, '_omnix_fast_visible_dialogue_hook_installed', False)
assert getattr(runtime, '_omnix_dialogue_quality_hook_installed', False)
assert getattr(runtime, '_omnix_rpg_turn_job_mirror_installed', False)
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_direct_turn_route_rejects_missing_session_before_applying_turn(monkeypatch) -> None:
    from app.rpg.session import interactive_first_call_runtime
    from app.rpg.session import service

    calls: list[dict[str, object]] = []

    def apply_turn(session_id: str, command: str, performance_override: dict[str, object] | None = None) -> dict[str, object]:
        calls.append({
            "session_id": session_id,
            "command": command,
            "performance_override": performance_override,
        })
        return {
            "ok": True,
            "final_narration": "Bran nods from behind the bar.",
            "session": {"state": {"session_id": session_id, "turn_count": 1}},
        }

    monkeypatch.setattr(interactive_first_call_runtime, "apply_turn", apply_turn)
    monkeypatch.setattr(service, "load_session", lambda session_id: None)

    app = FastAPI(title="test")
    include_router_registrar(app, register_rpg_session_routes)

    response = TestClient(app).post("/api/rpg/sessions/rpg_test/turn", json={"command": "i ask bran how he is doing"})

    assert response.status_code == 404
    payload = response.json()
    assert payload["detail"]["error"] == "session_not_found"
    assert calls == []


def test_direct_turn_route_does_not_start_job_for_missing_session(monkeypatch) -> None:
    from app.rpg.session import interactive_first_call_runtime
    from app.rpg.session import service

    calls: list[str] = []

    def apply_turn(session_id: str, command: str, performance_override: dict[str, object] | None = None) -> dict[str, object]:
        calls.append(session_id)
        return {
            "ok": True,
            "final_narration": "Bran says the hearth is warm and the day is kind.",
            "session": {"state": {"session_id": session_id, "turn_count": 1}},
        }

    monkeypatch.setattr(interactive_first_call_runtime, "apply_turn", apply_turn)
    monkeypatch.setattr(service, "load_session", lambda session_id: None)
    monkeypatch.delattr(interactive_first_call_runtime, "_omnix_rpg_turn_job_mirror_installed", raising=False)

    install_rpg_turn_job_mirror_hook()
    app = FastAPI(title="Omnix Web Gateway")
    include_router_registrar(app, register_rpg_session_routes)

    response = TestClient(app).post("/api/rpg/sessions/rpg_job/turn", json={"command": "i ask bran how he is doing"})

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "session_not_found"
    assert calls == []


def test_direct_turn_route_rejects_missing_command() -> None:
    app = FastAPI(title="test")
    include_router_registrar(app, register_rpg_session_routes)

    response = TestClient(app).post("/api/rpg/sessions/rpg_test/turn", json={})

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "missing_command"
