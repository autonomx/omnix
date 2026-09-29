"""Phase 12.13 — Visual queue tests."""

import pytest

from app.jobs import store as job_store_module
from app.rpg.visual.job_queue import (
    claim_next_visual_job,
    complete_visual_job,
    enqueue_visual_job,
    list_visual_jobs,
    prune_completed_visual_jobs,
    release_visual_job,
)
from tests.support.in_memory_jobs import InMemoryJobStore


@pytest.fixture
def visual_job_store(monkeypatch, tmp_path):
    store = InMemoryJobStore(tmp_path / "visual-jobs")
    monkeypatch.setattr(job_store_module, "default_job_store", lambda: store)
    return store


def test_enqueue_dedupes_same_active_job(visual_job_store):
    job1 = enqueue_visual_job(session_id="s1", request_id="r1")
    job2 = enqueue_visual_job(session_id="s1", request_id="r1")
    assert job1["request_id"] == job2["request_id"]
    jobs = list_visual_jobs()
    assert len(jobs) == 1


def test_claim_and_complete_job(visual_job_store):
    enqueue_visual_job(session_id="s1", request_id="r1")
    claimed = claim_next_visual_job(lease_seconds=60)
    assert claimed["status"] == "leased"
    assert claimed["lease_token"] != ""
    completed = complete_visual_job(job_id=claimed["job_id"], lease_token=claimed["lease_token"])
    assert completed["status"] == "complete"


def test_stale_leased_job_can_be_reclaimed(visual_job_store):
    enqueue_visual_job(session_id="s1", request_id="r1")
    claimed = claim_next_visual_job(lease_seconds=1)
    assert claimed["job_id"] != ""
    # Release job back to queue
    released = release_visual_job(job_id=claimed["job_id"], lease_token=claimed["lease_token"])
    assert released["status"] == "queued"
    # Claim again - should get same job
    reclaimed = claim_next_visual_job(lease_seconds=60)
    assert reclaimed["job_id"] == claimed["job_id"]
    assert reclaimed["lease_token"] != claimed["lease_token"]


def test_no_jobs_returns_empty(visual_job_store):
    result = claim_next_visual_job()
    assert result == {}


def test_release_job_returns_to_queued(visual_job_store):
    enqueue_visual_job(session_id="s1", request_id="r1")
    claimed = claim_next_visual_job(lease_seconds=60)
    released = release_visual_job(job_id=claimed["job_id"], lease_token=claimed["lease_token"])
    assert released["status"] == "queued"
    assert released["lease_token"] == ""


def test_complete_with_error_marks_failed(visual_job_store):
    enqueue_visual_job(session_id="s1", request_id="r1")
    claimed = claim_next_visual_job(lease_seconds=60)
    completed = complete_visual_job(job_id=claimed["job_id"], lease_token=claimed["lease_token"], error="test error")
    assert completed["status"] == "failed"
    assert completed["error"] == "test error"


def test_prune_completed_jobs_keeps_latest_finished_visual(visual_job_store):
    enqueue_visual_job(session_id="s1", request_id="r1")
    enqueue_visual_job(session_id="s2", request_id="r2")
    enqueue_visual_job(session_id="s3", request_id="r3")

    claimed = claim_next_visual_job(lease_seconds=60)
    complete_visual_job(job_id=claimed["job_id"], lease_token=claimed["lease_token"])
    claimed = claim_next_visual_job(lease_seconds=60)
    complete_visual_job(job_id=claimed["job_id"], lease_token=claimed["lease_token"])

    result = prune_completed_visual_jobs(keep_last=1)
    assert result["active"] == 1
    assert result["finished_kept"] == 1
    assert result["kept"] == 2
    assert result["pruned"] == 1


def test_wrong_lease_token_fails(visual_job_store):
    enqueue_visual_job(session_id="s1", request_id="r1")
    claimed = claim_next_visual_job(lease_seconds=60)
    result = complete_visual_job(job_id=claimed["job_id"], lease_token="wrong:token")
    assert result == {}
