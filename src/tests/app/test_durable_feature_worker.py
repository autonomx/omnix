from types import SimpleNamespace
import threading

import pytest

from app.composition.worker_runtime.durable_feature_worker import (
    _LeaseBoundJobStore,
    DurableFeatureJobWorker,
    execute_durable_feature_job,
)
from app.jobs.handlers import AnyJobInput, Backoff, JobHandlerRegistry, JobHandlerSpec
from app.jobs.models import FailJobRequest, ResourceClass
from app.persistence.execution_repositories import JobClaimConflict
from app.runtime.feature_catalog import FEATURE_CATALOG, load_feature


class _Store:
    def __init__(self):
        self.completed = []

    def get_job(self, job_id):
        return job_id

    def complete_job(self, job_id, request=None):
        self.completed.append(job_id)
        return job_id


def test_lease_bound_store_fences_mutations_to_its_job_and_token():
    from app.jobs.models import CompleteJobRequest

    class Store:
        def __init__(self):
            self.completed = []

        def get_job(self, job_id):
            return job_id

        def complete_job(self, job_id, request):
            self.completed.append((job_id, request.worker_id, request.lease_token))
            return job_id

    job = SimpleNamespace(
        id="job:1",
        lease=SimpleNamespace(worker_id="pool:cpu", token="lease:one"),
    )
    store = Store()
    fenced = _LeaseBoundJobStore(store, job)

    assert fenced.get_job("job:1") == "job:1"
    with pytest.raises(JobClaimConflict, match="cannot mutate another job"):
        fenced.complete_job("job:other", CompleteJobRequest())
    assert fenced.complete_job("job:1", CompleteJobRequest()) == "job:1"
    assert store.completed == [("job:1", "pool:cpu", "lease:one")]


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
        "assistant.memory.suggest",
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
    assert failures[0][1]._retry_delay_seconds == 8


def test_fail_job_retry_delay_is_not_part_of_public_request_schema():
    assert "retry_delay_seconds" not in FailJobRequest.model_json_schema()["properties"]


def test_registered_retry_delay_has_a_one_second_floor():
    registry = JobHandlerRegistry((
        JobHandlerSpec(
            type="feature.zero-delay",
            handler=lambda context, job: job,
            retry_backoff=Backoff(base_seconds=0, jitter=0),
        ),
    ))
    assert registry.retry_delay_seconds("feature.zero-delay", 1) == 1


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


def test_lease_bound_store_injects_credentials_for_mutations():
    events = []

    class Store:
        def update_progress(self, job_id, progress, **credentials):
            events.append(("progress", job_id, progress, credentials))
            return SimpleNamespace(status="running")

    job = SimpleNamespace(
        id="job:rpg",
        lease=SimpleNamespace(token="lease-token", worker_id="worker:test"),
    )
    fenced = _LeaseBoundJobStore(Store(), job)
    fenced.update_progress("job:rpg", progress={"current": 1})
    assert events == [(
        "progress",
        "job:rpg",
        {"current": 1},
        {"worker_id": "worker:test", "lease_token": "lease-token"},
    )]


def test_durable_feature_worker_runs_independent_jobs_concurrently(monkeypatch):
    registry = JobHandlerRegistry((
        JobHandlerSpec(
            type="feature.concurrent",
            handler=lambda context, job: job,
            resource_class=ResourceClass.CPU,
        ),
    ))
    worker = DurableFeatureJobWorker(
        object(),
        registry,
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

    def execute(_job, _cancellation):
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


def test_a_claimed_job_logs_under_its_submitting_request_id(monkeypatch):
    from app.observability.logging import current_log_context

    worker = DurableFeatureJobWorker(object(), JobHandlerRegistry(()), poll_seconds=0.01)
    seen = {}
    monkeypatch.setattr(worker, "_execute_claimed", lambda job, _cancellation: seen.update(current_log_context()))

    worker._run_claimed(
        SimpleNamespace(id="job:traced", module="feature", correlation_id="req-traced-0001"), threading.Event(),
    )

    assert seen["request_id"] == "req-traced-0001"
    assert seen["job_id"] == "job:traced"


def test_a_job_execution_is_timed_by_type_and_outcome(monkeypatch):
    from app.jobs.models import JobStatus
    from app.observability.metrics import exposition
    from app.composition.worker_runtime import durable_feature_worker

    def executions(outcome):
        prefix = f'omnix_job_execution_seconds_count{{job_type="feature.timed",outcome="{outcome}"}} '
        lines = [line for line in exposition()[0].decode().splitlines() if line.startswith(prefix)]
        return float(lines[0].split()[-1]) if lines else 0.0

    worker = DurableFeatureJobWorker(object(), JobHandlerRegistry(()), poll_seconds=0.01)
    job = SimpleNamespace(id="job:timed", type="feature.timed",
                          lease=SimpleNamespace(worker_id="worker-1", token="lease-1"))
    results = iter([SimpleNamespace(status=JobStatus.COMPLETED), RuntimeError("handler crashed")])

    def execute(*_args, **_kwargs):
        result = next(results)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(durable_feature_worker, "execute_durable_feature_job", execute)
    monkeypatch.setattr(worker, "_record_unexpected_failure", lambda *_args: None)
    completed, errors = executions("completed"), executions("error")

    worker._execute_claimed(job, threading.Event())
    worker._execute_claimed(job, threading.Event())

    assert executions("completed") - completed == 1
    assert executions("error") - errors == 1
