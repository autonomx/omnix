"""Dubbing's durable jobs: one per pipeline step (``dub.<step>``), all through ``execute_dub_step``."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.jobs.handlers import JobExecutionContext
from app.jobs.models import CompleteJobRequest, CreateJobRequest, FailJobRequest, JobRecord, ResourceClass
from app.persistence.database import default_database
from app.runtime.tenant_context import current_tenant

from . import service
from .steps import CHAINED, STEPS, DubRequestError, StepRun

JOB_TYPES = {f"dub.{step}": step for step in STEPS}
RESOURCE_CLASSES = {
    "ingest": ResourceClass.CPU,
    "separate": ResourceClass.GPU_AUDIO,
    "transcribe": ResourceClass.GPU_STT,
    "translate": ResourceClass.GPU_LLM,
    "cast": ResourceClass.CPU,
    "synthesize": ResourceClass.GPU_TTS,
    "mux": ResourceClass.CPU,
}


class DubStepInput(BaseModel):
    project_id: str = Field(min_length=1, max_length=200)
    # Submit the next step when this one finishes (review stops the chain before mux).
    chain: bool = False
    # Only these lines (translate, synthesize); empty means every line that needs it.
    line_ids: list[str] = Field(default_factory=list, max_length=2000)


def _failure(exc: Exception) -> tuple[str, bool]:
    from app.platform.voice.contracts import AudioToolRequestError

    if isinstance(exc, (DubRequestError, service.DubbingNotFound, AudioToolRequestError)):
        return "invalid_request", False
    return "dubbing_step_failed", True


def _run(step: str, run: StepRun, database: Any, tenant: Any) -> dict[str, Any]:
    from . import steps

    project_id = run.project["id"]
    if step == "translate":
        from .translate import Translator

        return steps.translate(run, Translator(run.project.get("translator") or ""))
    if step == "cast":
        from app.platform.voice.contracts import clone_voice

        def clone(*, name: str, wav: bytes, text: str, language: str) -> str:
            return clone_voice(run.job, run.job_store, name=name, wav=wav, reference_text=text, language=language)

        return steps.cast(run, clone)
    if step == "synthesize":
        from app.providers.service import pinned_tts_provider, selected_tts_provider_id
        from app.providers.tts_priority import generation_class

        from .translate import Translator

        engine = run.project.get("engine") or selected_tts_provider_id()
        with generation_class("offline"):
            return steps.synthesize(
                run, provider=pinned_tts_provider(engine), engine=engine,
                translator=Translator(run.project.get("translator") or ""),
                save_translation=lambda segment_id, text, revision: service.save_translation(
                    database, tenant, project_id, segment_id, text, "shortened", expected_revision=revision),
                save_take=lambda segment_id, **take: service.save_take(database, tenant, project_id, segment_id, **take),
            )
    return getattr(steps, step)(run)


def execute_dub_step(context: JobExecutionContext, job: JobRecord) -> JobRecord:
    store = context.job_store
    store.mark_running(job.id)
    step = JOB_TYPES[job.type]
    request = DubStepInput.model_validate(job.input_payload or {})
    database, tenant = default_database(), current_tenant()
    try:
        project, segments = service.load_for_step(database, tenant, request.project_id)
        service.mark_step(database, tenant, request.project_id, step, "running", job_id=job.id)
        result = _run(step, StepRun(job, store, project, segments), database, tenant)
        summary = service.apply_step_result(database, tenant, request.project_id, result)
        service.mark_step(database, tenant, request.project_id, step, "done", job_id=job.id, detail=summary)
    except Exception as exc:
        from app.platform.voice.contracts import wait_for_engine

        deferred = wait_for_engine(store, job, exc)
        if deferred is not None:
            service.mark_step(database, tenant, request.project_id, step, "waiting", job_id=job.id,
                              error="waiting for the TTS engine to be swapped in")
            return deferred
        code, retryable = _failure(exc)
        try:
            service.mark_step(database, tenant, request.project_id, step, "failed", job_id=job.id, error=str(exc))
        except service.DubbingNotFound:
            pass  # the project was deleted while the step ran
        failed = store.fail_job(job.id, FailJobRequest(code=code, message=str(exc) or "The dubbing step failed",
                                                       retryable=retryable,
                                                       details={"step": step, "project_id": request.project_id}))
        return failed or job
    if request.chain and step in CHAINED:
        following = CHAINED[step]
        # Once per finishing step: a step that runs again after a lost lease does not queue its follow-up twice.
        follow_up = store.create_job_once(CreateJobRequest(
            module="dubbing", type=f"dub.{following}", resource_class=RESOURCE_CLASSES[following], priority=0,
            input_payload={"project_id": request.project_id, "chain": True},
        ), idempotency_key=f"dub-chain:{job.id}")
        service.mark_step(database, tenant, request.project_id, following, "queued", job_id=follow_up.id)
    completed = store.complete_job(job.id, CompleteJobRequest(output_refs=[
        {"type": "dub_step", "module": "dubbing", "project_id": request.project_id, "step": step, **summary},
    ]))
    return completed or job


__all__ = ["DubStepInput", "JOB_TYPES", "RESOURCE_CLASSES", "execute_dub_step"]
