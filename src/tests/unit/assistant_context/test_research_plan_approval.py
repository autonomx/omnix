from __future__ import annotations

from app.jobs import ClaimJobRequest, CreateJobRequest, JobStatus, ResourceClass
from app.testing.in_memory_job_store import InMemoryJobStore


def test_plan_approval_jobs_are_not_claimed_by_background_workers(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_INLINE_RESEARCH_JOB_EXECUTOR", "0")
    store = InMemoryJobStore(tmp_path / "jobs")
    waiting = store.create_job(
        CreateJobRequest(
            module="assistant",
            type="assistant.deep_research",
            resource_class=ResourceClass.NETWORK,
            priority=100,
            input_payload={"awaiting_plan_approval": True},
        )
    )
    runnable = store.create_job(
        CreateJobRequest(
            module="assistant",
            type="assistant.deep_research",
            resource_class=ResourceClass.NETWORK,
            input_payload={"awaiting_plan_approval": False},
        )
    )

    claim = store.claim_next(
        ClaimJobRequest(
            worker_id="worker:test",
            resource_classes=[ResourceClass.NETWORK],
        )
    )

    assert claim.ok
    assert claim.job is not None
    assert claim.job.id == runnable.id
    waiting_after_claim = store.get_job(waiting.id)
    assert waiting_after_claim is not None
    assert waiting_after_claim.status == JobStatus.QUEUED
