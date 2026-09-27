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
        from app.jobs.models import CompleteJobRequest
        store.complete_job("job:1", CompleteJobRequest())
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


@pytest.mark.parametrize("live", [True, False])
def test_rpg_executor_checks_its_actual_store_before_applying_the_turn(monkeypatch, live):
    from app.jobs import inline_feature_jobs

    events = []

    class Store:
        def mark_running(self, job_id):
            assert job_id == "job:rpg"

        def require_execution_authority(self, job_id):
            assert job_id == "job:rpg"
            events.append("authority")
            if not live:
                raise RuntimeError("authority lost")

        def complete_job(self, job_id, request):
            assert request.output_refs[0]["content"] == "A guarded turn"
            return SimpleNamespace(status="completed")

        def fail_job(self, job_id, request):
            assert request.message == "authority lost"
            return SimpleNamespace(status="failed")

    def apply_turn(session_id, command):
        assert (session_id, command) == ("session:rpg", "look")
        events.append("apply")
        return {"response": "A guarded turn"}

    # The compatibility package re-exports functions loaded under a private
    # source module; their globals are owned by that implementation namespace.
    implementation = inline_feature_jobs._render_job.__globals__
    monkeypatch.setitem(implementation, "_apply_authoritative_rpg_turn", apply_turn)
    monkeypatch.setitem(implementation, "_rpg_turn_visible_text", lambda result: result["response"])
    job = SimpleNamespace(id="job:rpg", type="rpg.turn", module="rpg", input_payload={"command": "look"}, input_ref={"session_id": "session:rpg"})
    result = inline_feature_jobs.execute_inline_feature_job(Store(), job)
    assert result.status == ("completed" if live else "failed")
    assert events == (["authority", "apply"] if live else ["authority"])

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

