"""Deferred narration runs as rpg.narration jobs (WP-5.6)."""
from __future__ import annotations

import copy

import pytest

from app.apps.rpg.session import interaction_lifecycle, narration_jobs, session_runtime_store
from app.apps.rpg.session.jobs import narration_job
from app.jobs.models import JobStatus
from tests.support.in_memory_jobs import InMemoryJobStore

SESSION_ID = "session:narration-job"


@pytest.fixture
def world(monkeypatch, tmp_path):
    sessions: dict[str, dict] = {
        SESSION_ID: {
            "manifest": {"session_id": SESSION_ID, "id": SESSION_ID},
            "runtime_state": {
                "tick": 4,
                "interaction_id_by_turn": {"turn:4": "interaction:4"},
                "interaction_lifecycles": {
                    "interaction:4": {"interaction_id": "interaction:4", "turn_id": "turn:4",
                                      "status": "narration_pending", "narration_status": "queued"},
                },
                "interaction_timeline": {"events": [{"interaction_id": "interaction:4", "turn_id": "turn:4"}]},
            },
        }
    }
    saves: list[dict] = []
    events: list[dict] = []
    narrated: list[str] = []

    def load(session_id):
        stored = sessions.get(session_id)
        return copy.deepcopy(stored) if stored is not None else None

    def save(session):
        sessions[session["manifest"]["session_id"]] = copy.deepcopy(session)
        saves.append(session)
        return session

    def narrate(scene, context, **kwargs):
        narrated.append(str(context.get("player_input")))
        return {
            "narration": "Rain drums on the tavern roof.",
            "used_llm": True,
            "narration_json": {
                "format_version": "rpg_narration_v2", "narration": "Rain drums on the tavern roof.",
                "action": "You listen.", "npc": {"speaker": "", "line": ""}, "reward": None, "followup_hooks": [],
            },
        }

    for module in (session_runtime_store, narration_jobs):
        monkeypatch.setattr(module, "load_runtime_session", load)
        monkeypatch.setattr(module, "save_runtime_session", save)
    monkeypatch.setattr(narration_jobs, "narrate_scene", narrate)
    monkeypatch.setattr(narration_jobs, "build_app_llm_gateway", lambda: None)
    monkeypatch.setattr(narration_jobs, "publish_narration_event", lambda session_id, event: events.append(event) or 1)
    jobs = InMemoryJobStore(tmp_path / "jobs")  # in-memory stores share state per path
    return {"sessions": sessions, "saves": saves, "events": events, "narrated": narrated, "jobs": jobs}


def _enqueue(jobs):
    return narration_job.enqueue_rpg_narration(
        SESSION_ID, "turn:4",
        {"turn_id": "turn:4", "tick": 4, "narration_context": {"player_input": "I listen"}},
        interaction_id="interaction:4", tick=4, job_store=jobs,
    )


def _run(jobs, job_id):
    job = jobs.get_job(job_id)
    return narration_job.execute_rpg_narration_job(jobs, job)


def test_a_queued_narration_job_narrates_the_turn_and_completes_its_interaction(world) -> None:
    queued = _enqueue(world["jobs"])
    assert queued["status"] == "queued"

    finished = _run(world["jobs"], queued["job_id"])

    assert finished.status == JobStatus.COMPLETED
    runtime = world["sessions"][SESSION_ID]["runtime_state"]
    assert runtime["narration_artifacts_by_turn"]["turn:4"]["narration"] == "Rain drums on the tavern roof."
    lifecycle = runtime["interaction_lifecycles"]["interaction:4"]
    assert (lifecycle["status"], lifecycle["narration_status"]) == ("narration_complete", "complete")
    assert "narration_jobs" not in runtime, "the queue no longer lives in the session"
    assert {"narration_complete", "narration_artifact"} <= {event.get("type") for event in world["events"]}


def test_a_duplicate_job_for_a_narrated_turn_completes_without_another_model_call(world) -> None:
    first = _enqueue(world["jobs"])
    _run(world["jobs"], first["job_id"])
    assert _enqueue(world["jobs"])["job_id"] == first["job_id"], "one job per turn"

    outcome = narration_jobs.run_narration_request(SESSION_ID, "turn:4", {"turn_id": "turn:4"})

    assert outcome == {"ok": True, "status": "completed", "turn_id": "turn:4", "deduped": True}
    assert world["narrated"] == ["I listen"]


def test_generation_failures_retry_and_the_last_attempt_marks_the_narration_failed(world, monkeypatch) -> None:
    monkeypatch.setattr(
        narration_jobs, "_generate_turn_narration_artifact",
        lambda *args, **kwargs: {"ok": False, "error": "provider_unavailable"},
    )
    queued = _enqueue(world["jobs"])
    job = world["jobs"].get_job(queued["job_id"])

    job._attempt_count = 1
    retried = narration_job.execute_rpg_narration_job(world["jobs"], job)
    lifecycle = world["sessions"][SESSION_ID]["runtime_state"]["interaction_lifecycles"]["interaction:4"]
    assert retried.status != JobStatus.COMPLETED and lifecycle["status"] == "narration_pending"

    job = world["jobs"].get_job(queued["job_id"])
    job._attempt_count = narration_job.MAX_ATTEMPTS
    narration_job.execute_rpg_narration_job(world["jobs"], job)
    lifecycle = world["sessions"][SESSION_ID]["runtime_state"]["interaction_lifecycles"]["interaction:4"]
    assert lifecycle["status"] == "narration_failed"
    assert lifecycle["narration_error"] == "provider_unavailable"
    assert any(event.get("status") == "failed" for event in world["events"])


def test_the_rpg_feature_registers_the_narration_handler() -> None:
    from app.apps.rpg.feature import FEATURE

    spec = next(spec for spec in FEATURE.job_handlers if spec.type == narration_job.JOB_TYPE)
    assert spec.max_attempts == narration_job.MAX_ATTEMPTS
    assert spec.resource_class.value == "gpu:llm"
