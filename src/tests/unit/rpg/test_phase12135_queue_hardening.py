"""Phase 12.13.5 — Queue hardening tests."""
from __future__ import annotations

from app.rpg.visual.job_queue import (
    claim_next_visual_job,
    complete_visual_job,
    enqueue_visual_job,
    list_visual_jobs,
    normalize_visual_queue,
    release_visual_job,
)
from app.rpg.visual.queue_runner import run_one_queued_job


def test_normalize_visual_queue_reclaims_stale_lease(monkeypatch, tmp_path):
    monkeypatch.setenv("RPG_VISUAL_QUEUE_DIR", str(tmp_path))
    enqueue_visual_job(session_id="s1", request_id="r1")
    claimed = claim_next_visual_job(lease_seconds=0)
    assert claimed["status"] == "leased"

    out = normalize_visual_queue()
    jobs = out["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["status"] == "queued"
    assert jobs[0]["lease_token"] == ""


def test_enqueue_visual_job_dedupes_existing_active_job(monkeypatch, tmp_path):
    monkeypatch.setenv("RPG_VISUAL_QUEUE_DIR", str(tmp_path))
    j1 = enqueue_visual_job(session_id="s1", request_id="r1")
    j2 = enqueue_visual_job(session_id="s1", request_id="r1")
    jobs = list_visual_jobs()
    assert len(jobs) == 1
    assert j1["request_id"] == j2["request_id"]


def test_complete_visual_job_rejects_wrong_lease(monkeypatch, tmp_path):
    monkeypatch.setenv("RPG_VISUAL_QUEUE_DIR", str(tmp_path))
    enqueue_visual_job(session_id="s1", request_id="r1")
    claimed = claim_next_visual_job(lease_seconds=60)
    bad = complete_visual_job(job_id=claimed["job_id"], lease_token="wrong-token")
    assert bad == {}
    jobs = list_visual_jobs()
    assert jobs[0]["status"] == "leased"


def test_release_visual_job_rejects_wrong_lease(monkeypatch, tmp_path):
    monkeypatch.setenv("RPG_VISUAL_QUEUE_DIR", str(tmp_path))
    enqueue_visual_job(session_id="s1", request_id="r1")
    claimed = claim_next_visual_job(lease_seconds=60)
    bad = release_visual_job(job_id=claimed["job_id"], lease_token="wrong-token")
    assert bad == {}
    jobs = list_visual_jobs()
    assert jobs[0]["status"] == "leased"


def test_run_one_queued_job_completes_terminal_request(monkeypatch, tmp_path):
    monkeypatch.setenv("RPG_VISUAL_QUEUE_DIR", str(tmp_path))

    session_store = {
        "s1": {
            "simulation_state": {
                "presentation_state": {
                    "visual_state": {
                        "image_requests": [
                            {
                                "request_id": "r1",
                                "status": "pending",
                                "error": "",
                            }
                        ]
                    }
                }
            }
        }
    }

    def _load_session_from_disk(session_id):
        return session_store.get(session_id)

    def _save_session_to_disk(session):
        session_store[session.get("manifest", {}).get("id", "s1")] = session

    def _process_pending_image_requests(simulation_state, limit=1):
        simulation_state["presentation_state"]["visual_state"]["image_requests"][0]["status"] = "complete"
        return simulation_state

    monkeypatch.setattr("app.rpg.visual.queue_runner.load_session_from_disk", _load_session_from_disk)
    monkeypatch.setattr("app.rpg.visual.queue_runner.save_session_to_disk", _save_session_to_disk)
    monkeypatch.setattr("app.rpg.visual.queue_runner.process_pending_image_requests", _process_pending_image_requests)

    enqueue_visual_job(session_id="s1", request_id="r1")
    result = run_one_queued_job()
    assert result["ok"] is True
    assert result["request_status"] == "complete"
    jobs = list_visual_jobs()
    assert jobs[0]["status"] == "complete"


def test_run_one_queued_job_requeues_pending_request(monkeypatch, tmp_path):
    monkeypatch.setenv("RPG_VISUAL_QUEUE_DIR", str(tmp_path))

    session_store = {
        "s1": {
            "simulation_state": {
                "presentation_state": {
                    "visual_state": {
                        "image_requests": [
                            {
                                "request_id": "r1",
                                "status": "pending",
                                "error": "temporary",
                            }
                        ]
                    }
                }
            }
        }
    }

    def _load_session_from_disk(session_id):
        return session_store.get(session_id)

    def _save_session_to_disk(session):
        session_store[session.get("manifest", {}).get("id", "s1")] = session

    def _process_pending_image_requests(simulation_state, limit=1):
        return simulation_state

    monkeypatch.setattr("app.rpg.visual.queue_runner.load_session_from_disk", _load_session_from_disk)
    monkeypatch.setattr("app.rpg.visual.queue_runner.save_session_to_disk", _save_session_to_disk)
    monkeypatch.setattr("app.rpg.visual.queue_runner.process_pending_image_requests", _process_pending_image_requests)

    enqueue_visual_job(session_id="s1", request_id="r1")
    result = run_one_queued_job()
    assert result["ok"] is True
    assert result["request_status"] == "pending"
    jobs = list_visual_jobs()
    assert jobs[0]["status"] == "queued"


def test_run_one_queued_job_releases_on_exception(monkeypatch, tmp_path):
    monkeypatch.setenv("RPG_VISUAL_QUEUE_DIR", str(tmp_path))

    def _load_session_from_disk(_session_id):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.rpg.visual.queue_runner.load_session_from_disk", _load_session_from_disk)

    enqueue_visual_job(session_id="s1", request_id="r1")
    result = run_one_queued_job()
    assert result["ok"] is False
    jobs = list_visual_jobs()
    assert jobs[0]["status"] == "queued"
    assert jobs[0]["error"] == "boom"


def test_run_one_queued_job_handles_missing_request_after_run(monkeypatch, tmp_path):
    monkeypatch.setenv("RPG_VISUAL_QUEUE_DIR", str(tmp_path))

    session_store = {
        "s1": {
            "simulation_state": {
                "presentation_state": {
                    "visual_state": {
                        "image_requests": []
                    }
                }
            }
        }
    }

    def _load_session_from_disk(session_id):
        return session_store.get(session_id)

    def _save_session_to_disk(session):
        session_store[session.get("manifest", {}).get("id", "s1")] = session

    def _process_pending_image_requests(simulation_state, limit=1):
        return simulation_state

    monkeypatch.setattr("app.rpg.visual.queue_runner.load_session_from_disk", _load_session_from_disk)
    monkeypatch.setattr("app.rpg.visual.queue_runner.save_session_to_disk", _save_session_to_disk)
    monkeypatch.setattr("app.rpg.visual.queue_runner.process_pending_image_requests", _process_pending_image_requests)

    enqueue_visual_job(session_id="s1", request_id="r1")
    result = run_one_queued_job()
    assert result["ok"] is False
    jobs = list_visual_jobs()
    assert jobs[0]["status"] == "queued"
    assert jobs[0]["error"] == "request_not_found_after_run"


def test_queue_job_attempts_increment(monkeypatch, tmp_path):
    """Test that job attempts increment on each claim."""
    monkeypatch.setenv("RPG_VISUAL_QUEUE_DIR", str(tmp_path))
    enqueue_visual_job(session_id="s1", request_id="r1")

    claimed = claim_next_visual_job(lease_seconds=0)
    assert claimed["attempts"] == 1

    release_visual_job(job_id=claimed["job_id"], lease_token=claimed["lease_token"])

    jobs = list_visual_jobs()
    assert jobs[0]["status"] == "queued"

    claimed2 = claim_next_visual_job(lease_seconds=60)
    assert claimed2["attempts"] == 2