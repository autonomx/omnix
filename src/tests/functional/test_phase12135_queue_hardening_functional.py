"""Phase 12.13.5 — Queue hardening functional tests."""
from __future__ import annotations

import json
from io import StringIO

from app.rpg.visual.job_queue import (
    claim_next_visual_job,
    complete_visual_job,
    enqueue_visual_job,
    list_visual_jobs,
    normalize_visual_queue,
    release_visual_job,
)
from app.rpg.visual.queue_runner import run_one_queued_job


def test_queue_hardening_end_to_end(monkeypatch, tmp_path):
    """Test complete queue lifecycle with hardening features."""
    monkeypatch.setenv("RPG_VISUAL_QUEUE_DIR", str(tmp_path))

    # Enqueue two jobs
    j1 = enqueue_visual_job(session_id="s1", request_id="r1")
    j2 = enqueue_visual_job(session_id="s2", request_id="r2")
    assert j1["status"] == "queued"
    assert j2["status"] == "queued"

    # Verify deduplication
    j3 = enqueue_visual_job(session_id="s1", request_id="r1")
    jobs = list_visual_jobs()
    assert len(jobs) == 2

    # Claim first job
    claimed = claim_next_visual_job(lease_seconds=300)
    assert claimed["status"] == "leased"
    assert claimed["attempts"] == 1

    # Complete the job
    completed = complete_visual_job(
        job_id=claimed["job_id"],
        lease_token=claimed["lease_token"],
    )
    assert completed["status"] == "complete"


def test_queue_stale_lease_recovery(monkeypatch, tmp_path):
    """Test that stale leases are automatically recovered."""
    monkeypatch.setenv("RPG_VISUAL_QUEUE_DIR", str(tmp_path))

    enqueue_visual_job(session_id="s1", request_id="r1")
    claimed = claim_next_visual_job(lease_seconds=0)
    assert claimed["status"] == "leased"

    # After normalize, should be queued again
    normalized = normalize_visual_queue()
    assert normalized["jobs"][0]["status"] == "queued"


def test_queue_multiple_sessions(monkeypatch, tmp_path):
    """Test queue handling multiple sessions with same request."""
    monkeypatch.setenv("RPG_VISUAL_QUEUE_DIR", str(tmp_path))

    j1 = enqueue_visual_job(session_id="session_a", request_id="portrait:1")
    j2 = enqueue_visual_job(session_id="session_b", request_id="portrait:1")

    jobs = list_visual_jobs()
    # Different sessions = different jobs
    assert len(jobs) == 2


def test_queue_run_one_with_no_jobs(monkeypatch, tmp_path):
    """Test running queue when empty returns no jobs available."""
    monkeypatch.setenv("RPG_VISUAL_QUEUE_DIR", str(tmp_path))
    result = run_one_queued_job()
    assert result["ok"] is True
    assert result["processed"] is False
    assert result["reason"] == "no_job_available"


def test_queue_complete_with_error(monkeypatch, tmp_path):
    """Test completing a job with error marks it as failed."""
    monkeypatch.setenv("RPG_VISUAL_QUEUE_DIR", str(tmp_path))

    enqueue_visual_job(session_id="s1", request_id="r1")
    claimed = claim_next_visual_job(lease_seconds=60)
    completed = complete_visual_job(
        job_id=claimed["job_id"],
        lease_token=claimed["lease_token"],
        error="Generation failed",
    )
    assert completed["status"] == "failed"
    assert completed["error"] == "Generation failed"


def test_queue_lease_token_validation(monkeypatch, tmp_path):
    """Test that invalid lease tokens are rejected."""
    monkeypatch.setenv("RPG_VISUAL_QUEUE_DIR", str(tmp_path))

    enqueue_visual_job(session_id="s1", request_id="r1")
    claimed = claim_next_visual_job(lease_seconds=60)

    result = complete_visual_job(
        job_id=claimed["job_id"],
        lease_token="invalid_token",
    )
    assert result == {}

    result = release_visual_job(
        job_id=claimed["job_id"],
        lease_token="invalid_token",
    )
    assert result == {}