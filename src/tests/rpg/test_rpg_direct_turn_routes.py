from __future__ import annotations
from tests.support.routers import include_router_registrar

import os
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.rpg.api.feature_routes.rpg_session_routes import register_rpg_session_routes


def test_gateway_fresh_start_uses_explicit_turn_pipeline_and_job_mirror() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo_root / "src")
    script = """
from app.gateway.main import create_gateway_app
app = create_gateway_app()
from app.rpg.jobs.turn_job_mirror import execute_turn_with_job_mirror
from app.rpg.session import interactive_first_call_runtime as runtime
from app.rpg.session.pipeline import TURN_PIPELINE
assert callable(execute_turn_with_job_mirror)
assert [stage.name for stage in TURN_PIPELINE]
assert not hasattr(runtime, '_omnix_rpg_turn_job_mirror_installed')
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
