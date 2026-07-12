from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.rpg_session_routes import register_rpg_session_routes
from app.gateway.rpg_turn_job_mirror import install_rpg_turn_job_mirror_hook
from app.jobs.rpg_turn_job_guard import RPG_FOREGROUND_RECORD_TYPE


def test_gateway_fresh_start_installs_required_rpg_turn_hooks() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo_root / "src")
    script = """
from app.gateway.main import app
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


def test_direct_turn_route_applies_runtime_without_job_queue(monkeypatch) -> None:
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
    monkeypatch.setattr(service, "save_session", lambda session, compact=False: {"state": session["state"], "saved": True})

    app = FastAPI(title="test")
    register_rpg_session_routes(app)

    response = TestClient(app).post("/api/rpg/sessions/rpg_test/turn", json={"command": "i ask bran how he is doing"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["session_id"] == "rpg_test"
    assert payload["command"] == "i ask bran how he is doing"
    assert payload["response"] == "Bran nods from behind the bar."
    assert payload["content"] == "Bran nods from behind the bar."
    assert "session" not in payload
    assert calls == [
        {
            "session_id": "rpg_test",
            "command": "i ask bran how he is doing",
            "performance_override": {
                "enable_live_narration_llm": True,
                "narration_mode": "blocking",
            },
        }
    ]


def test_direct_turn_route_persists_completed_rpg_turn_job(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OMNIX_JOBS_DB_PATH", str(tmp_path / "jobs.sqlite"))

    from app.rpg.session import interactive_first_call_runtime
    from app.rpg.session import service

    def apply_turn(session_id: str, command: str, performance_override: dict[str, object] | None = None) -> dict[str, object]:
        return {
            "ok": True,
            "final_narration": "Bran says the hearth is warm and the day is kind.",
            "session": {"state": {"session_id": session_id, "turn_count": 1}},
        }

    monkeypatch.setattr(interactive_first_call_runtime, "apply_turn", apply_turn)
    monkeypatch.delattr(interactive_first_call_runtime, "_omnix_rpg_turn_job_mirror_installed", raising=False)
    monkeypatch.setattr(service, "save_session", lambda session, compact=False: {"state": session["state"], "saved": True})

    install_rpg_turn_job_mirror_hook()
    app = FastAPI(title="Omnix Web Gateway")
    register_rpg_session_routes(app)

    response = TestClient(app).post("/api/rpg/sessions/rpg_job/turn", json={"command": "i ask bran how he is doing"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["creation_server_trace"]["job_id"].startswith("job:")

    from app.jobs.models import JobStatus
    from app.jobs.store import default_job_store

    jobs = default_job_store().list_jobs()
    assert len(jobs) == 1
    job = jobs[0]
    assert job.module == "rpg"
    assert job.type == RPG_FOREGROUND_RECORD_TYPE
    assert job.status == JobStatus.COMPLETED
    assert job.input_ref == {"session_id": "rpg_job"}
    assert job.input_payload is not None
    assert job.input_payload["command"] == "i ask bran how he is doing"
    assert job.output_refs[0]["type"] == "rpg_turn_response"
    assert job.output_refs[0]["content"] == "Bran says the hearth is warm and the day is kind."
    assert job.output_refs[0]["record_version"] == "rpg_foreground_turn_record_v1"
    assert job.output_refs[0]["turn_response"]["ok"] is True
    assert "session" not in job.output_refs[0]["turn_response"]
    assert job.completed_at is not None


def test_direct_turn_route_rejects_missing_command() -> None:
    app = FastAPI(title="test")
    register_rpg_session_routes(app)

    response = TestClient(app).post("/api/rpg/sessions/rpg_test/turn", json={})

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "missing_command"
