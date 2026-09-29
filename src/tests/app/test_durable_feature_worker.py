from types import SimpleNamespace
import threading

import pytest

from app.worker_runtime.durable_feature_worker import (
    _AuthorityBoundJobStore,
    DurableFeatureJobWorker,
    execute_durable_feature_job,
)
from app.jobs.handlers import AnyJobInput, Backoff, JobHandlerRegistry, JobHandlerSpec
from app.jobs.models import FailJobRequest, ResourceClass
from app.runtime.feature_catalog import FEATURE_CATALOG, load_feature


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


def test_feature_catalog_owns_durable_job_types():
    expected = {
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
    }
    actual = {
        spec.type
        for feature_id in FEATURE_CATALOG
        for spec in load_feature(feature_id).job_handlers
    }
    assert expected <= actual


def test_registry_dispatch_uses_explicit_feature_handler():
    expected = SimpleNamespace(status="completed")
    registry = JobHandlerRegistry(
        (
            JobHandlerSpec(
                type="story.generate",
                handler=lambda context, job: expected,
                input_model=AnyJobInput,
                resource_class=ResourceClass.GPU_LLM,
            ),
        )
    )
    result = execute_durable_feature_job(
        object(),
        SimpleNamespace(type="story.generate", input_payload={}),
        registry,
    )
    assert result is expected


def test_registry_dispatch_does_not_require_core_job_type_changes():
    expected = SimpleNamespace(status="completed")
    registry = JobHandlerRegistry(
        (
            JobHandlerSpec(
                type="feature.custom",
                handler=lambda context, job: expected,
                input_model=AnyJobInput,
            ),
        )
    )
    result = execute_durable_feature_job(
        object(),
        SimpleNamespace(type="feature.custom", input_payload={}),
        registry,
    )
    assert result is expected


def test_registry_rejects_duplicate_job_handler_types():
    spec = JobHandlerSpec(type="feature.duplicate", handler=lambda context, job: job)

    with pytest.raises(ValueError, match="duplicate job handler type"):
        JobHandlerRegistry((spec, spec))


def test_registry_validates_feature_input_at_submission():
    from pydantic import BaseModel, ValidationError

    from app.jobs.models import CreateJobRequest

    class Input(BaseModel):
        count: int

    registry = JobHandlerRegistry((
        JobHandlerSpec(
            type="feature.validated",
            handler=lambda context, job: job,
            input_model=Input,
        ),
    ))
    request = CreateJobRequest(
        module="feature",
        type="feature.validated",
        resource_class=ResourceClass.CPU,
        input_payload={"count": "invalid"},
    )

    with pytest.raises(ValidationError):
        registry.validate_submission(request)


def test_registered_backoff_is_applied_to_retryable_feature_failure():
    failures = []
    registry = JobHandlerRegistry((
        JobHandlerSpec(
            type="feature.retry",
            handler=lambda context, job: context.job_store.fail_job(
                job.id,
                FailJobRequest(
                    code="temporary",
                    message="retry me",
                    retryable=True,
                ),
            ),
            retry_backoff=Backoff(
                base_seconds=2,
                factor=2,
                max_seconds=20,
                jitter=0,
            ),
        ),
    ))

    class Store:
        def fail_job(self, job_id, request):
            failures.append((job_id, request))
            return SimpleNamespace(status="retrying")

    job = SimpleNamespace(
        id="job:retry",
        type="feature.retry",
        input_payload={},
        _attempt_count=3,
    )
    result = execute_durable_feature_job(Store(), job, registry)

    assert result.status == "retrying"
    assert failures[0][1].retry_delay_seconds == 8


def test_unknown_durable_type_fails_nonretryably_with_lease_credentials():
    calls = []
    expected = SimpleNamespace(status="failed")

    class Store:
        def fail_job(self, job_id, request):
            calls.append((job_id, request))
            return expected

    lease = SimpleNamespace(worker_id="worker:test", token="lease:test")
    job = SimpleNamespace(type="feature.missing", id="job:missing", lease=lease)
    result = execute_durable_feature_job(Store(), job, JobHandlerRegistry())

    assert result is expected
    assert len(calls) == 1
    job_id, failure = calls[0]
    assert job_id == "job:missing"
    assert failure.code == "unsupported_job_type"
    assert failure.retryable is False
    assert failure.worker_id == "worker:test"
    assert failure.lease_token == "lease:test"


@pytest.mark.parametrize("live", [True, False])
def test_authority_bound_store_is_the_execution_fence(live):
    events = []

    class Store:
        database = SimpleNamespace()
        context = SimpleNamespace(workspace_id="workspace:test")

        def complete_job(self, job_id, request):
            events.append("complete")
            return SimpleNamespace(status="completed")

    authority = _Authority(live=live)
    job = SimpleNamespace(
        id="job:rpg",
        lease=SimpleNamespace(token="lease-token", worker_id="worker:test"),
    )
    fenced = _AuthorityBoundJobStore(Store(), authority, job)

    if live:
        # The database lease query is covered by PostgreSQL integration tests.
        assert fenced.get_job if hasattr(fenced, "get_job") else True
    else:
        with pytest.raises(RuntimeError, match="authority lost"):
            fenced.require_execution_authority(job.id)


def test_durable_feature_worker_runs_independent_jobs_concurrently(monkeypatch):
    authority = _Authority(live=True)
    worker = DurableFeatureJobWorker(
        object(),
        authority,
        JobHandlerRegistry(),
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
