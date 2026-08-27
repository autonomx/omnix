"""Background execution for durable assistant Deep Research jobs."""
from __future__ import annotations

import os
import threading
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.research.contracts import RESEARCH_JOB_TYPE
from app.research.deep_research_diagnostics import deep_research_log
from app.research.executor import DeepResearchExecutor, ResearchExecutionCheckpoint
from app.research.jobs import DeepResearchJobInput
from app.research.synthesis import DeepResearchSynthesizer

from .models import (
    CancelJobRequest,
    CompleteJobRequest,
    FailJobRequest,
    JobRecord,
    JobStatus,
)
from .inline_execution_compat import mark_inline_execution

RESEARCH_EXECUTOR_ENV = "OMNIX_INLINE_RESEARCH_JOB_EXECUTOR"
_RESEARCH_THREADS_LOCK = threading.Lock()
_RESEARCH_THREAD_JOB_IDS: set[str] = set()
ResearchWorkflow = Callable[
    [DeepResearchJobInput, Callable[[str, str], None], Callable[[], bool]],
    "DeepResearchWorkflowResult",
]


class DeepResearchWorkflowResult(BaseModel):
    content: str
    research_status: str = "partial"
    source_manifest_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)


class _IdentityBoundQuickSearch:
    def __init__(self, service: Any, identity: str) -> None:
        self.service = service
        self.identity = identity

    def search(self, query: str, max_results: int) -> Any:
        return self.service.search(query, max_results, identity=self.identity)


def install_research_job_execution(sqlite_job_store_cls: Any) -> None:
    """Patch job creation once so Deep Research runs after the route returns."""

    if getattr(sqlite_job_store_cls, "_omnix_research_jobs_installed", False):
        return
    original_create_job = sqlite_job_store_cls.create_job

    def create_job_with_research_execution(self: Any, request: Any) -> JobRecord:
        awaiting_approval = _awaiting_plan_approval(request)
        if request.type == RESEARCH_JOB_TYPE and _executor_enabled() and not awaiting_approval:
            request = mark_inline_execution(request)
        job = original_create_job(self, request)
        if job.type == RESEARCH_JOB_TYPE and _executor_enabled() and not awaiting_approval:
            start_research_job(self, job)
        return job

    sqlite_job_store_cls.create_job = create_job_with_research_execution
    sqlite_job_store_cls._omnix_research_jobs_installed = True


def execute_research_job(
    job_store: Any,
    job: JobRecord,
    *,
    workflow_fn: ResearchWorkflow | None = None,
    chat_store: Any | None = None,
) -> JobRecord:
    """Execute one durable research job and persist a normal assistant message."""

    try:
        request = DeepResearchJobInput.model_validate(job.input_payload or {})
    except ValidationError as exc:
        deep_research_log(job.id, "invalid_request", error_type=type(exc).__name__, error=str(exc))
        return _fail(job_store, job, "research_invalid_request", str(exc), retryable=False)

    if chat_store is None:
        from app.chat import default_chat_store

        chat_store = default_chat_store()
    if workflow_fn is None:
        resume = load_research_checkpoint(job_store, job.id)

        def workflow_fn(
            request: DeepResearchJobInput,
            progress: Callable[[str, str], None],
            canceled: Callable[[], bool],
        ) -> DeepResearchWorkflowResult:
            return _default_workflow(
                request,
                progress,
                canceled,
                checkpoint=resume,
                save_checkpoint=lambda stage_id, state: save_research_checkpoint(
                    job_store,
                    job.id,
                    stage_id,
                    state,
                ),
            )

    if _cancel_requested(job_store, job.id):
        deep_research_log(job.id, "cancel_before_start")
        return _finalize_canceled(job_store, job.id, "Canceled before research started") or job

    deep_research_log(
        job.id,
        "job_start",
        session_id=request.session_id,
        user_message_id=request.user_message_id,
        provider=request.research_provider,
        provider_chain=request.research_provider_chain,
        max_steps=request.max_steps,
        max_queries=request.max_queries,
        max_sources=request.max_sources,
        max_extracts=request.max_extracts,
    )
    current = job_store.get_job(job.id)
    if current is None:
        deep_research_log(job.id, "job_missing_before_execution")
        return job
    if current.status == JobStatus.RUNNING:
        job = current
    else:
        job = job_store.mark_running(job.id) or current
    _stage(job_store, job.id, "planning", "Planning research")

    def progress(stage_id: str, message: str) -> None:
        _stage(job_store, job.id, stage_id, message)

    def canceled() -> bool:
        return _cancel_requested(job_store, job.id)

    try:
        result = workflow_fn(request, progress, canceled)
    except Exception as exc:
        deep_research_log(
            job.id,
            "workflow_failed",
            error_type=type(exc).__name__,
            error=str(exc) or "Deep Research failed",
        )
        return _fail(
            job_store,
            job,
            "research_workflow_failed",
            str(exc) or "Deep Research failed",
            retryable=True,
        )

    if canceled() or result.research_status == "canceled":
        deep_research_log(job.id, "cancel_during_research", research_status=result.research_status)
        return _finalize_canceled(job_store, job.id, "Canceled during research") or job

    deep_research_log(
        job.id,
        "workflow_result",
        research_status=result.research_status,
        content_length=len(result.content or ""),
        source_manifest_id=result.source_manifest_id,
        stop_reason=result.output.get("stop_reason"),
        logical_queries=result.output.get("logical_queries"),
        extracted_pages=result.output.get("extracted_pages"),
        source_count=len(result.output.get("sources") or []),
        warning_count=len(result.output.get("warnings") or []),
        search_diagnostics=result.output.get("search_diagnostics"),
    )
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
        deep_research_log(
            job.id,
            "chat_persist_missing",
            session_id=request.session_id,
            user_message_id=request.user_message_id,
            content_length=len(result.content or ""),
        )
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
    assistant_message = next(
        (
            message
            for message in reversed(saved.messages)
            if message.role == "assistant"
            and (getattr(message, "metadata", {}) or {}).get("research_job_id") == job.id
        ),
        None,
    )
    deep_research_log(
        job.id,
        "job_completed",
        session_id=saved.id,
        message_count=len(saved.messages),
        assistant_message_id=getattr(assistant_message, "id", None),
        assistant_content_length=len(getattr(assistant_message, "content", "") or ""),
        job_status=getattr(completed or job, "status", None),
    )
    return completed or job


def save_research_checkpoint(
    job_store: Any,
    job_id: str,
    stage_id: str,
    checkpoint: ResearchExecutionCheckpoint,
) -> JobRecord | None:
    job = job_store.get_job(job_id)
    if job is None or job.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELED}:
        return job
    stages = [
        stage.model_copy(update={"checkpoint_ref": checkpoint.model_dump(mode="json")})
        if stage.id == stage_id
        else stage
        for stage in job.stages
    ]
    update_stages = getattr(job_store, "update_job_stages", None)
    if callable(update_stages):
        return update_stages(job_id, stages)
    deep_research_log(job_id, "checkpoint_not_persisted", stage_id=stage_id)
    return job


def load_research_checkpoint(
    job_store: Any,
    job_id: str,
) -> ResearchExecutionCheckpoint | None:
    job = job_store.get_job(job_id)
    if job is None:
        return None
    checkpoints: list[ResearchExecutionCheckpoint] = []
    for stage in job.stages:
        if not stage.checkpoint_ref:
            continue
        try:
            checkpoints.append(ResearchExecutionCheckpoint.model_validate(stage.checkpoint_ref))
        except ValidationError:
            continue
    return max(checkpoints, key=lambda item: item.next_operation_index, default=None)


def start_research_job(job_store: Any, job: JobRecord) -> JobRecord:
    current = job_store.get_job(job.id) or job
    if current.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELED}:
        return current
    if _awaiting_plan_approval(current):
        deep_research_log(job.id, "job_waiting_for_plan_approval")
        return current
    with _RESEARCH_THREADS_LOCK:
        if job.id in _RESEARCH_THREAD_JOB_IDS:
            return current
        _RESEARCH_THREAD_JOB_IDS.add(job.id)
    running = job_store.mark_running(job.id) or current

    def run() -> None:
        try:
            execute_research_job(job_store, running)
        except Exception as exc:
            deep_research_log(
                job.id,
                "worker_start_failed",
                error_type=type(exc).__name__,
                error=str(exc) or "Deep Research worker failed to start",
            )
            current = job_store.get_job(job.id) or running
            try:
                _fail(
                    job_store,
                    current,
                    "research_worker_start_failed",
                    str(exc) or "Deep Research worker failed to start",
                    retryable=True,
                )
            except Exception as fail_exc:
                deep_research_log(
                    job.id,
                    "worker_failure_not_persisted",
                    error_type=type(fail_exc).__name__,
                    error=str(fail_exc),
                )
        finally:
            with _RESEARCH_THREADS_LOCK:
                _RESEARCH_THREAD_JOB_IDS.discard(job.id)

    thread = threading.Thread(
        target=run,
        name=f"omnix-research-{job.id.removeprefix('job:')[:8]}",
        daemon=True,
    )
    thread.start()
    return running


def _executor_enabled() -> bool:
    return os.environ.get(RESEARCH_EXECUTOR_ENV, "1").strip().lower() not in {
        "0", "false", "off", "disabled"
    }


def _stage(job_store: Any, job_id: str, stage_id: str, message: str) -> None:
    job = job_store.get_job(job_id)
    if job is None:
        deep_research_log(job_id, "stage_missing_job", stage_id=stage_id, message=message)
        return
    deep_research_log(job_id, "stage", stage_id=stage_id, message=message)
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
        deep_research_log(job_id, "cancel_missing_job", reason=reason)
        return None
    finalize_cancel = getattr(job_store, "finalize_cancel", None)
    if callable(finalize_cancel):
        saved = finalize_cancel(job_id, reason)
    else:
        saved = job_store.cancel_job(job_id, CancelJobRequest(reason=reason))
    deep_research_log(job_id, "job_canceled", reason=reason)
    return saved or job


def _awaiting_plan_approval(request: Any) -> bool:
    payload = getattr(request, "input_payload", None)
    return isinstance(payload, dict) and payload.get("awaiting_plan_approval") is True


def _fail(
    job_store: Any,
    job: JobRecord,
    code: str,
    message: str,
    *,
    retryable: bool,
) -> JobRecord:
    deep_research_log(job.id, "job_failed", code=code, message=message, retryable=retryable)
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
    *,
    checkpoint: ResearchExecutionCheckpoint | None = None,
    save_checkpoint: Callable[[str, ResearchExecutionCheckpoint], None] | None = None,
) -> DeepResearchWorkflowResult:
    from app.assistant_context.web_search import WebSearchClient
    from app.research.extraction import ReadablePageExtractor
    from app.research.planner import ResearchPlanner
    from app.research.policy import research_policy_from_env
    from app.research.provider_chain import ProviderFallbackSearchClient, normalize_provider_chain
    from app.research.quick_search import QuickSearchService

    policy = replace(
        research_policy_from_env(),
        search_cache_ttl_seconds=request.search_cache_ttl_seconds,
        extraction_cache_ttl_seconds=request.extraction_cache_ttl_seconds,
    )
    provider_chain = normalize_provider_chain(
        request.research_provider,
        request.research_provider_chain,
    )

    def quick_search_factory(remaining_sources: int, remaining_extracts: int) -> Any:
        service = QuickSearchService(
            client_factory=lambda timeout: ProviderFallbackSearchClient(
                providers=provider_chain,
                timeout_seconds=timeout,
                client_factory=WebSearchClient,
            ),
            research_policy=policy,
            extractor_factory=lambda: ReadablePageExtractor(research_policy=policy),
            max_extracts=min(4, remaining_extracts),
            max_extract_workers=4 if "playwright" in provider_chain else 1,
        )
        return _IdentityBoundQuickSearch(service, request.session_id)

    execution = DeepResearchExecutor(
        planner=ResearchPlanner(prefer_hermes=request.hermes_planner_enabled),
        quick_search_factory=quick_search_factory,
        extractor_factory=lambda: ReadablePageExtractor(research_policy=policy),
    ).execute(
        request,
        progress,
        canceled,
        checkpoint=checkpoint,
        save_checkpoint=save_checkpoint,
    )
    if execution.research_status == "canceled":
        return DeepResearchWorkflowResult(
            content="Research was canceled.",
            research_status="canceled",
        )

    progress("synthesizing", "Writing the evidence-backed research answer")
    synthesis = DeepResearchSynthesizer().synthesize(
        execution,
        question=request.question,
        provider_id=request.provider_id,
        model_id=request.model_id,
    )
    research_status = (
        "partial"
        if synthesis.backend == "deterministic_fallback"
        else execution.research_status
    )
    combined_warnings = list(dict.fromkeys([*execution.warnings, *synthesis.warnings]))
    return DeepResearchWorkflowResult(
        content=synthesis.content,
        research_status=research_status,
        source_manifest_id=execution.source_manifest_id,
        metadata={
            "research_provider": request.research_provider,
            "research_provider_chain": list(provider_chain),
            "research_budget": {
                "max_steps": request.max_steps,
                "max_queries": request.max_queries,
                "max_sources": request.max_sources,
                "max_extracts": request.max_extracts,
            },
            "planner_backend": execution.planner_backend,
            "synthesis_backend": synthesis.backend,
            "synthesis_validation": synthesis.validation.model_dump(mode="json"),
            "research_stop_reason": execution.stop_reason,
            "research_warnings": combined_warnings,
            "search_diagnostics": execution.search_diagnostics,
            "conflict_count": len(execution.conflicts),
            "logical_queries": execution.logical_queries,
            "extracted_pages": execution.extracted_pages,
            **synthesis.provider_metadata,
        },
        output={
            "objective": execution.objective,
            "research_provider": request.research_provider,
            "research_provider_chain": list(provider_chain),
            "research_budget": {
                "max_steps": request.max_steps,
                "max_queries": request.max_queries,
                "max_sources": request.max_sources,
                "max_extracts": request.max_extracts,
            },
            "planner_backend": execution.planner_backend,
            "synthesis_backend": synthesis.backend,
            "synthesis_validation": synthesis.validation.model_dump(mode="json"),
            "answer_sections": [item.model_dump(mode="json") for item in synthesis.sections],
            "stop_reason": execution.stop_reason,
            "warnings": combined_warnings,
            "search_diagnostics": execution.search_diagnostics,
            "sources": [item.model_dump(mode="json") for item in execution.sources],
            "snapshots": [item.model_dump(mode="json") for item in execution.snapshots],
            "evidence": [item.model_dump(mode="json") for item in execution.evidence],
            "conflicts": [item.model_dump(mode="json") for item in execution.conflicts],
            "logical_queries": execution.logical_queries,
            "extracted_pages": execution.extracted_pages,
        },
    )
