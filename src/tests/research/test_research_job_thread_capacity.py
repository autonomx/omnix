from types import SimpleNamespace

from app.jobs.models import JobStatus
from app.platform.research import jobs as research_jobs


def test_research_thread_dispatch_respects_capacity(monkeypatch) -> None:
    monkeypatch.setattr(research_jobs, "_MAX_RESEARCH_THREAD_JOBS", 1)
    monkeypatch.setattr(
        research_jobs,
        "_RESEARCH_THREAD_JOB_IDS",
        {"job:already-running"},
    )
    current = SimpleNamespace(
        id="job:queued",
        status=JobStatus.QUEUED,
        input_payload={},
    )

    class _Store:
        def get_job(self, _job_id):
            return current

        def mark_running(self, _job_id):
            raise AssertionError("capacity-rejected jobs must remain queued")

    assert research_jobs.start_research_job(_Store(), current) is current
    assert research_jobs._RESEARCH_THREAD_JOB_IDS == {"job:already-running"}
