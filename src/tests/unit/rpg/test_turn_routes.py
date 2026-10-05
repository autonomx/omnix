"""Route contract for the RPG turn endpoint (WP-3.3c, required architecture gate)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.apps.rpg.api.feature_routes.rpg_session_routes import register_rpg_session_routes
from tests.support.routers import include_router_registrar


def _turn_client() -> TestClient:
    app = FastAPI(title="rpg-turn-routes")
    include_router_registrar(app, register_rpg_session_routes)
    return TestClient(app)


def _record_apply_turn(monkeypatch) -> list[str]:
    from app.apps.rpg.session import interactive_first_call_runtime

    calls: list[str] = []

    def apply_turn(session_id: str, command: str, performance_override: dict[str, object] | None = None):
        calls.append(session_id)
        return {"ok": True, "final_narration": "unused", "session": {"state": {"session_id": session_id}}}

    monkeypatch.setattr(interactive_first_call_runtime, "apply_turn", apply_turn)
    return calls


def test_turn_for_missing_session_is_rejected_before_any_turn_is_applied(monkeypatch) -> None:
    from app.apps.rpg.session import service

    calls = _record_apply_turn(monkeypatch)
    monkeypatch.setattr(service, "load_session", lambda session_id: None)

    response = _turn_client().post("/api/rpg/sessions/rpg_missing/turn", json={"command": "look around"})

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "session_not_found"
    assert calls == []


def test_turn_stages_run_off_the_event_loop(monkeypatch) -> None:
    # Session load and save, presentation and projection read or write
    # PostgreSQL or call a model; on the loop they stall every other request.
    import threading

    from app.apps.rpg.session import service

    threads: dict[str, int] = {}

    def load_session(session_id: str):
        threads["load_session"] = threading.get_ident()
        return None

    monkeypatch.setattr(service, "load_session", load_session)
    app = FastAPI(title="rpg-turn-routes")
    include_router_registrar(app, register_rpg_session_routes)

    @app.get("/loop-thread")
    async def loop_thread() -> dict[str, int]:
        return {"ident": threading.get_ident()}

    with TestClient(app) as client:  # one event loop thread for both requests
        loop_ident = client.get("/loop-thread").json()["ident"]
        response = client.post("/api/rpg/sessions/rpg_missing/turn", json={"command": "look around"})
        assert client.get("/loop-thread").json()["ident"] == loop_ident

    assert response.status_code == 404
    assert threads["load_session"] != loop_ident


def test_turn_without_a_command_is_rejected(monkeypatch) -> None:
    calls = _record_apply_turn(monkeypatch)

    response = _turn_client().post("/api/rpg/sessions/rpg_any/turn", json={})

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "missing_command"
    assert calls == []


def test_gateway_composition_uses_the_explicit_turn_pipeline_without_installers() -> None:
    # A fresh interpreter proves composition, not test import order, wires the pipeline.
    repo_root = Path(__file__).resolve().parents[4]
    script = """
from app.composition.gateway.main import create_gateway_app
create_gateway_app()
from app.apps.rpg.jobs.turn_job_mirror import execute_turn_with_job_mirror
from app.apps.rpg.session import interactive_first_call_runtime as runtime
from app.apps.rpg.session.pipeline import TURN_PIPELINE
assert callable(execute_turn_with_job_mirror)
assert [stage.name for stage in TURN_PIPELINE]
assert not hasattr(runtime, '_omnix_rpg_turn_job_mirror_installed')
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        env={**os.environ, "PYTHONPATH": str(repo_root / "src")},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
