"""Full dossiers for a turn's newcomers, written after the turn (``rpg.scene_lore``).

A turn that meets a person, creature or place the campaign's canon does not yet
describe merges a built-in dossier, marked provisional, so it can narrate at
once; this job asks the model for the full one and replaces it. The jobs system
owns the claim and the retries; a retry after a conflicting turn reads the
bible again.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.jobs.models import CompleteJobRequest, CreateJobRequest, FailJobRequest, JobRecord, ResourceClass

JOB_TYPE = "rpg.scene_lore"
MAX_ATTEMPTS = 3


class RpgSceneLoreJobInput(BaseModel):
    """The campaign and the targets whose provisional dossiers to write in full."""

    model_config = ConfigDict(extra="allow")
    campaign_id: str = Field(min_length=1)
    targets: list[dict[str, str]] = Field(default_factory=list)


def enqueue_scene_lore_enrichment(
    campaign_id: str,
    targets: list[dict[str, str]],
    *,
    job_store: Any = None,
) -> dict[str, Any]:
    """Queue one enrichment per (campaign, targets); a repeat returns the same job."""
    from app.jobs.store import default_job_store

    store = job_store if job_store is not None else default_job_store()
    payload = RpgSceneLoreJobInput(campaign_id=campaign_id, targets=targets)
    key = ",".join(sorted(str(target.get("entity_id") or "") for target in targets))
    job = store.create_job_once(
        CreateJobRequest(
            module="rpg",
            type=JOB_TYPE,
            resource_class=ResourceClass.GPU_LLM,
            # Below a player's turn and its narration: newcomers' dossiers can wait for them.
            priority=10,
            input_ref={"campaign_id": campaign_id},
            input_payload=payload.model_dump(mode="json"),
        ),
        idempotency_key=f"{JOB_TYPE}:{campaign_id}:{key}",
    )
    return {"job_id": job.id, "status": str(getattr(job.status, "value", job.status))}


def execute_scene_lore_job(job_store: Any, job: JobRecord) -> JobRecord:
    from .runtime_lore_store import enrich_scene_lore

    request = RpgSceneLoreJobInput.model_validate(job.input_payload or {})
    attempt = max(1, int(getattr(job, "_attempt_count", 0) or 1))
    job_store.mark_running(job.id)
    try:
        report = enrich_scene_lore(request.campaign_id, request.targets)
    except Exception as exc:
        failed = job_store.fail_job(
            job.id,
            FailJobRequest(
                code="rpg_scene_lore_failed",
                message=str(exc) or "RPG scene lore enrichment failed",
                retryable=attempt < MAX_ATTEMPTS,
                details={"campaign_id": request.campaign_id, "attempt": attempt},
            ),
        )
        return failed or job
    completed = job_store.complete_job(
        job.id,
        CompleteJobRequest(
            output_refs=[{
                "type": "rpg_scene_lore",
                "module": "rpg",
                "campaign_id": request.campaign_id,
                "enriched_entity_ids": list(report.get("enriched_entity_ids") or ()),
            }],
        ),
    )
    return completed or job


__all__ = [
    "JOB_TYPE",
    "MAX_ATTEMPTS",
    "RpgSceneLoreJobInput",
    "enqueue_scene_lore_enrichment",
    "execute_scene_lore_job",
]
