"""A job's run returns its result or raises; the registry settles the job (deep-modules wave 2)."""
from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.jobs.errors import JobClaimConflict
from app.jobs.handlers import (
    JobExecutionContext,
    JobHandlerRegistry,
    JobHandlerSpec,
    JobResult,
    PermanentJobError,
    RetryableJobError,
)
from app.jobs.models import CancelJobRequest, CreateJobRequest, JobStatus, ResourceClass
from tests.support.in_memory_jobs import InMemoryJobStore


class _Input(BaseModel):
    word: str


def _registry(run, *, max_attempts: int = 3) -> JobHandlerRegistry:
    return JobHandlerRegistry((JobHandlerSpec(type="test.echo", run=run, failure_code="echo_failed",
                                              input_model=_Input, max_attempts=max_attempts),))


def _execute(tmp_path, run, *, attempt: int = 1, max_attempts: int = 3):
    store = InMemoryJobStore(tmp_path / "jobs")
    job = store.create_job(CreateJobRequest(module="test", type="test.echo", resource_class=ResourceClass.CPU,
                                            input_payload={"word": "hello"}))
    store.mark_running(job.id)
    job = store.get_job(job.id)
    job._attempt_count = attempt
    return _registry(run, max_attempts=max_attempts).execute(JobExecutionContext(job_store=store), job)


def test_a_result_completes_the_job_with_its_outputs(tmp_path) -> None:
    seen = []

    def run(job_run):
        seen.append((job_run.input.word, job_run.attempt, job_run.final_attempt))
        return JobResult(output_refs=({"type": "echo", "content": job_run.input.word},),
                         logs=({"level": "info", "message": "echoed"},))

    finished = _execute(tmp_path, run)

    assert finished.status == JobStatus.COMPLETED and finished.output_refs[0]["content"] == "hello"
    assert seen == [("hello", 1, False)]


def test_a_job_failure_fails_the_job_under_its_code(tmp_path) -> None:
    def run(job_run):
        raise PermanentJobError("echo_refused", "no echo today", details={"why": "quiet"})

    failed = _execute(tmp_path, run)

    assert failed.status == JobStatus.FAILED
    assert (failed.error.code, failed.error.message, failed.error.retryable) == ("echo_refused", "no echo today", False)
    assert failed.error.details == {"job_type": "test.echo", "module": "test", "why": "quiet"}


def test_any_other_exception_fails_under_the_specs_code_and_is_retried(tmp_path) -> None:
    def run(job_run):
        raise RuntimeError("the model went away")

    failed = _execute(tmp_path, run)

    assert (failed.error.code, failed.error.message, failed.error.retryable) == (
        "echo_failed", "the model went away", True)


def test_the_final_attempt_is_not_retryable(tmp_path) -> None:
    def run(job_run):
        assert job_run.final_attempt
        raise RetryableJobError("echo_busy", "busy")

    failed = _execute(tmp_path, run, attempt=2, max_attempts=2)

    assert failed.error.code == "echo_busy" and failed.error.retryable is False


def test_a_lost_lease_publishes_nothing(tmp_path) -> None:
    def run(job_run):
        raise JobClaimConflict("lease lost")

    with pytest.raises(JobClaimConflict):
        _execute(tmp_path, run)


def test_a_run_that_settled_its_job_returns_that_record(tmp_path) -> None:
    def run(job_run):
        return job_run.store.cancel_job(job_run.job.id, CancelJobRequest()) or job_run.job

    settled = _execute(tmp_path, run)

    assert settled.status != JobStatus.COMPLETED


def test_a_spec_names_exactly_one_handler_and_a_run_names_its_failure_code() -> None:
    def run(job_run):
        return JobResult()

    with pytest.raises(ValueError, match="exactly one"):
        JobHandlerSpec(type="test.none")
    with pytest.raises(ValueError, match="exactly one"):
        JobHandlerSpec(type="test.both", run=run, handler=lambda context, job: job, failure_code="x")
    with pytest.raises(ValueError, match="failure_code"):
        JobHandlerSpec(type="test.uncoded", run=run)
