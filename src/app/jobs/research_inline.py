"""Background execution for durable assistant Deep Research jobs."""
from __future__ import annotations

import os
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.research.contracts import RESEARCH_JOB_TYPE
from app.research.jobs import DeepResearchJobInput

from .models import (
    CancelState,
    CompleteJobRequest,
    FailJobRequest,
    JobProgress,
    JobRecord,
    JobStatus,
)

RESEARCH_EXECUTOR_ENV = "OMNIX_INLINE_RESEARCH_JOB_EXECUTOR"


class DeepResearchWorkflowResult(BaseModel):
    content: str
    research_status: str = "partial"
    source_manifest_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)


def install_research_job_execution(sqlite_job_store_cls: Any) -> None:
    """Patch job creation once so Deep Research runs after the route returns."""

    if getattr(sqlite_job_store_cls, "_omnix_research_jobs_installed", False):
        return
    original_create_job = sqlite_job_store_cls.create_job

    def create_job_with_research_execution(self: Any, request: Any) -> JobRecord:
        job = original_create_job(self, request)
        if job.type == RESEARCH_JOB_TYPE and _executor_enabled():
            _start_research_job(self, job)
        return job

    sqlite_job_store_cls.create_job = create_job_with_research_execution
    sqlite_job_store_cls._omnix_research_jobs_installed = True


def execute_research_job(
    job_store: Any,
    job: JobRecord,
    *,
    workflow_fn: Callable[[DeepResearchJobInput, Callable[[str, str], None], Callable[[], bool]], DeepResearchWorkflowResult] | None = None,
    chat_store: Any | None = None,
) -> JobRecord:
    """Execute one durable research job and persist a normal assistant message."""

    try:
        request = DeepResearchJobInput.model_validate(job.input_payload or {})
    except ValidationError as exc:
        return _fail(job_store, job, "research_invalid_request", str(exc), retryable=False)

    if chat_store is None:
        from app.chat import default_chat_store

        chat_store = default_chat_store()
    if workflow_fn is None:
        workflow_fn = _default_workflow

    if _cancel_requested(job_store, job.id):
        return _finalize_canceled(job_store, job.id, "Canceled before research started") or job

    job_store.mark_running(job.id)
    _stage(job_store, job.id, "planning", "Planning research")

    def progress(stage_id: str, message: str) -> None:
        _stage(job_store, job.id, stage_id, message)

    def canceled() -> bool:
        return _cancel_requested(job_store, job.id)

    try:
        result = workflow_fn(request, progress, canceled)
    except Exception as exc:
        return _fail(
            job_store,
            job,
            "research_workflow_failed",
            str(exc) or "Deep Research failed",
            retryable=True,
        )

    if canceled():
        return _finalize_canceled(job_store, job.id, "Canceled during research") or job

    _stage(job_store, job.id, "persisting", "Saving research result")
    metadata = {
        "generation_status": "completed",
        "research_mode": "deep",
        "research_status": result.research_status,
        "research_job_id": job.id,
        "source_manifest_id": result.source_manifest_id,
        **result.metadata,
    }
    saved = chat_store.complete_streamed_reply(
        request.session_id,
        request.user_message_id,
        result.content,
        metadata,
    )
    if saved is None:
        return _fail(
            job_store,
            job,
            "research_chat_session_missing",
            "Deep Research completed but the chat session could not be updated",
            retryable=False,
        )

    completed = job_store.complete_job(
        job.id,
        CompleteJobRequest(
            output_refs=[
                {
                    "type": "research",
                    "research_status": result.research_status,
                    "session_id": request.session_id,
                    "message_id": request.user_message_id,
                    "source_manifest_id": result.source_manifest_id,
                    **result.output,
                }
            ],
            logs=[{"level": "info", "message": "Deep Research result persisted to chat"}],
        ),
    )
    return completed or job


def _start_research_job(job_store: Any, job: JobRecord) -> None:
    thread = threading.Thread(
        target=execute_research_job,
        args=(job_store, job),
        name=f"omnix-research-{job.id.removeprefix('job:')[:8]}",
        daemon=True,
    )
    thread.start()


def _executor_enabled() -> bool:
    return os.environ.get(RESEARCH_EXECUTOR_ENV, "1").strip().lower() not in {
        "0", "false", "off", "disabled"
    }


def _stage(job_store: Any, job_id: str, stage_id: str, message: str) -> None:
    job = job_store.get_job(job_id)
    if job is None:
        return
    total = max(1, len(job.stages))
    index = next((i for i, stage in enumerate(job.stages) if stage.id == stage_id), 0)
    for prior in job.stages[:index]:
        if prior.status != JobStatus.COMPLETED:
            job_store.update_progress(
                job_id,
                current=index,
                total=total,
                message=f"Completed {prior.label}",
                stage_id=prior.id,
                stage_status=JobStatus.COMPLETED,
            )
    job_store.update_progress(
        job_id,
        current=index,
        total=total,
        message=message,
        stage_id=stage_id,
        stage_status=JobStatus.RUNNING,
    )


def _cancel_requested(job_store: Any, job_id: str) -> bool:
    current = job_store.get_job(job_id)
    return bool(current and (current.cancel.requested or current.status == JobStatus.CANCEL_REQUESTED))


def _finalize_canceled(job_store: Any, job_id: str, reason: str) -> JobRecord | None:
    job = job_store.get_job(job_id)
    if job is None:
        return None
    now = datetime.now(timezone.utc).isoformat()
    job.status = JobStatus.CANCELED
    job.updated_at = now
    job.completed_at = now
    job.lease = None
    job.cancel = CancelState(
        requested=True,
        requested_at=job.cancel.requested_at or now,
        acknowledged_at=now,
        reason=job.cancel.reason or reason,
    )
    job.progress = JobProgress(current=job.progress.current, total=job.progress.total, message="canceled")
    job.stages = [
        stage.model_copy(
            update={
                "status": JobStatus.CANCELED if stage.status == JobStatus.RUNNING else stage.status,
                "completed_at": now if stage.status == JobStatus.RUNNING else stage.completed_at,
            }
        )
        for stage in job.stages
    ]
    return job_store._save_with_event(job, "job.canceled")  # noqa: SLF001 - shared job adapter


def _fail(
    job_store: Any,
    job: JobRecord,
    code: str,
    message: str,
    *,
    retryable: bool,
) -> JobRecord:
    failed = job_store.fail_job(
        job.id,
        FailJobRequest(
            code=code,
            message=message,
            retryable=retryable,
            details={"job_type": job.type, "module": job.module},
        ),
    )
    return failed or job


def _default_workflow(
    request: DeepResearchJobInput,
    progress: Callable[[str, str], None],
    canceled: Callable[[], bool],
) -> DeepResearchWorkflowResult:
    """Safe WSR-4 fallback replaced by the planner/executor phases."""

    progress("searching", "Preparing bounded research execution")
    if canceled():
        return DeepResearchWorkflowResult(content="Research was canceled.", research_status="canceled")
    progress("synthesizing", "Writing a partial research response")
    return DeepResearchWorkflowResult(
        content=(
            "Deep Research was queued successfully, but the iterative research planner is not enabled yet.\n\n"
            "## Limitations\nNo external sources were evaluated for this result."
        ),
        research_status="partial",
        metadata={"limitations": ["research_planner_not_enabled"]},
        output={"limitations": ["research_planner_not_enabled"]},
    )
