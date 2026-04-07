"""Phase 12.13.5 — Queue hardening regression tests.

Ensures that queue hardening changes do not break existing behavior:
- Queue operations remain backward compatible
- Existing job status transitions work correctly
- Job deduplication doesn't lose valid jobs
- Stale lease recovery doesn't corrupt queue state
"""
from __future__ import annotations

from app.rpg.visual.job_queue import (
    claim_next_visual_job,
    complete_visual_job,
    enqueue_visual_job,
    list_visual_jobs,
    normalize_visual_queue,
    prune_completed_visual_jobs,
    release_visual_job,
)


def test_backward_compatible_job_structure(monkeypatch, tmp_path):
    """Ensure job structure maintains backward compatibility."""
    monkeypatch.setenv("RPG_VISUAL_QUEUE_DIR", str(tmp_path))

    job = enqueue_visual_job(session_id="s1", request_id="r1")

    # Verify all expected fields exist
    assert "job_id" in job
    assert "request_id" in job
    assert "session_id" in job
    assert "status" in job
    assert "lease_token" in job
    assert "lease_expires_at" in job
    assert "created_at" in job
    assert "updated_at" in job
    assert "completed_at" in job
    assert "error" in job
    assert "attempts" in job


def test_existing_queue_lifecycle_still_works(monkeypatch, tmp_path):
    """Test that standard queue lifecycle continues to work after hardening."""
    monkeypatch.setenv("RPG_VISUAL_QUEUE_DIR", str(tmp_path))

    # Enqueue
    job = enqueue_visual_job(session_id="s1", request_id="r1")
    assert job["status"] == "queued"

    # List
    jobs = list_visual_jobs()
    assert len(jobs) == 1

    # Claim
    claimed = claim_next_visual_job(lease_seconds=60)
    assert claimed["status"] == "leased"

    # Complete
    completed = complete_visual_job(
        job_id=claimed["job_id"],
        lease_token=claimed["lease_token"],
    )
    assert completed["status"] == "complete"

    # Prune
    result = prune_completed_visual_jobs(keep_last=10)
    assert result["active"] == 0


def test_deduplication_preserves_active_jobs(monkeypatch, tmp_path):
    """Ensure deduplication doesn't lose valid active jobs."""
    monkeypatch.setenv("RPG_VISUAL_QUEUE_DIR", str(tmp_path))

    # Create jobs for different sessions/requests
    enqueue_visual_job(session_id="s1", request_id="r1")
    enqueue_visual_job(session_id="s1", request_id="r2")
    enqueue_visual_job(session_id="s2", request_id="r1")

    # All should exist
    jobs = list_visual_jobs()
    assert len(jobs) == 3


def test_stale_lease_recovery_does_not_corrupt_queue(monkeypatch, tmp_path):
    """Ensure stale lease recovery maintains queue integrity."""
    monkeypatch.setenv("RPG_VISUAL_QUEUE_DIR", str(tmp_path))

    enqueue_visual_job(session_id="s1", request_id="r1")
    claimed = claim_next_visual_job(lease_seconds=0)

    # Force normalize (should reclaim stale lease)
    normalized = normalize_visual_queue()

    # Job should be back in queued state
    assert len(normalized["jobs"]) == 1
    assert normalized["jobs"][0]["status"] == "queued"

    # Should still be able to claim it
    claimed2 = claim_next_visual_job(lease_seconds=60)
    assert claimed2["status"] == "leased"


def test_duplicate_enqueue_returns_existing(monkeypatch, tmp_path):
    """Test that enqueueing same request returns existing active job."""
    monkeypatch.setenv("RPG_VISUAL_QUEUE_DIR", str(tmp_path))

    j1 = enqueue_visual_job(session_id="s1", request_id="r1")
    j2 = enqueue_visual_job(session_id="s1", request_id="r1")

    # Should return same job ID
    assert j1["job_id"] == j2["job_id"]
    assert j1["status"] == j2["status"]


def test_queue_file_persistence(monkeypatch, tmp_path):
    """Ensure queue data persists across operations."""
    monkeypatch.setenv("RPG_VISUAL_QUEUE_DIR", str(tmp_path))

    enqueue_visual_job(session_id="s1", request_id="r1")
    enqueue_visual_job(session_id="s2", request_id="r2")

    # List should return both jobs
    jobs = list_visual_jobs()
    assert len(jobs) == 2

    # After pruning with high keep_last, should still have both
    result = prune_completed_visual_jobs(keep_last=100)
    assert result["kept"] == 2