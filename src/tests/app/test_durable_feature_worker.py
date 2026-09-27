from types import SimpleNamespace
import threading

import pytest

from app.jobs.durable_feature_worker import (
    DURABLE_FEATURE_JOB_TYPES,
    _AuthorityBoundJobStore,
    execute_durable_feature_job,
)


class _Authority:
    def __init__(self, live=True):
        self.live = live
        self.checks = 0

    def require_live(self):
        self.checks += 1
        if not self.live:
            raise RuntimeError("authority lost")


class _Store:
    def __init__(self):
        self.completed = []

    def get_job(self, job_id):
        return job_id

    def complete_job(self, job_id, request=None):
        self.completed.append(job_id)
        return job_id


def test_authority_bound_store_fences_mutations_but_allows_reads():
    authority = _Authority(live=False)
    job = SimpleNamespace(id="job:1", lease=None)
    store = _AuthorityBoundJobStore(_Store(), authority, job)

    assert store.get_job("job:1") == "job:1"
    with pytest.raises(RuntimeError, match="authority lost"):
        store.complete_job("job:1")
    assert authority.checks == 1


def test_durable_feature_job_types_cover_legacy_execution_surfaces():
    assert {
        "story.generate",
        "podcast.generate",
        "rpg.turn",
        "rpg.report.last10",
        "tts.synthesize",
        "tts.multi_speaker_synthesize",
        "voice-cloning.create-profile",
        "voice-cloning.transcribe-sample",
        "image.generate",
        "assistant.deep_research",
    } == set(DURABLE_FEATURE_JOB_TYPES)


def test_story_dispatch_uses_explicit_executor(monkeypatch):
    from app.jobs import inline_feature_jobs

    expected = SimpleNamespace(status="completed")
    monkeypatch.setattr(
        inline_feature_jobs,
        "execute_inline_feature_job",
        lambda store, job: expected,
    )
    result = execute_durable_feature_job(
        object(),
        SimpleNamespace(type="story.generate"),
    )
    assert result is expected

def test_durable_feature_worker_runs_independent_jobs_concurrently(monkeypatch):
    from app.jobs.durable_feature_worker import DurableFeatureJobWorker

    authority = _Authority(live=True)
    worker = DurableFeatureJobWorker(
        object(),
        authority,
        poll_seconds=0.01,
        max_concurrency=2,
    )
    jobs = [SimpleNamespace(id="job:one"), SimpleNamespace(id="job:two")]
    entered = threading.Event()
    release = threading.Event()
    count_lock = threading.Lock()
    entered_count = 0

    def claim():
        return jobs.pop(0) if jobs else None

    def execute(_job):
        nonlocal entered_count
        with count_lock:
            entered_count += 1
            if entered_count == 2:
                entered.set()
        assert release.wait(2)

    monkeypatch.setattr(worker, "_claim_one", claim)
    monkeypatch.setattr(worker, "_execute_claimed", execute)
    try:
        worker.start()
        assert entered.wait(2)
        assert set(worker.active_job_ids) == {"job:one", "job:two"}
        assert worker.diagnostics()["max_concurrency"] == 2
    finally:
        release.set()
        worker.stop()

