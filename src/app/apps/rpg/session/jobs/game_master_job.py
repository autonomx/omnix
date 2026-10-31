"""The game master's direction, as a job after a turn commits (``rpg.game_master``; evolution roadmap EV-0).

Off the turn's path: it adds no latency and counts against no turn's model calls (F3). What it proposes is stored in
the proposal record (EV-11) for the next turn to fold in. One job a committed revision; a retry asks again.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field

from app.jobs.models import CompleteJobRequest, CreateJobRequest, FailJobRequest, JobRecord, ResourceClass

JOB_TYPE = "rpg.game_master"
MAX_ATTEMPTS = 2
logger = logging.getLogger(__name__)


class RpgGameMasterJobInput(BaseModel):
    model_config = ConfigDict(extra="allow")
    session_id: str = Field(min_length=1)
    revision: int = Field(ge=0)
    why: str = ""


# A job's place in the queue (the higher first): the player's narration 100, newcomers' dossiers 10; an area the hero
# may head to is filled before the one they stand in, and both before the game master's direction (EV-10's gate: a
# fill queued behind the direction jobs of a run of short moves was not done by the hero's arrival).
DIRECTION_PRIORITY, AREA_PRIORITY, AREA_HERE_PRIORITY = 5, 8, 7


def enqueue_game_master(session_id: str, revision: int, why: str, *, job_store: Any = None,
                        key: str = "", priority: int = DIRECTION_PRIORITY) -> dict[str, Any]:
    """The game master's job for a committed revision (``why``: its direction's reason, or ``fill:<area>`` to fill
    in an area, EV-10, keyed once a campaign by ``key``)."""
    from app.jobs.store import default_job_store

    store = job_store if job_store is not None else default_job_store()
    payload = RpgGameMasterJobInput(session_id=session_id, revision=revision, why=why)
    job = store.create_job_once(
        CreateJobRequest(module="rpg", type=JOB_TYPE, resource_class=ResourceClass.GPU_LLM,
                         priority=priority,
                         input_ref={"session_id": session_id, "revision": revision},
                         input_payload=payload.model_dump(mode="json")),
        idempotency_key=key or f"{JOB_TYPE}:{session_id}:{revision}",
    )
    return {"job_id": job.id, "status": str(getattr(job.status, "value", job.status))}


def after_commit(session_id: str, result: Mapping[str, Any], document: Mapping[str, Any], revision: int) -> None:
    """Queue the game master's direction when the committed turn calls for it; never fails the turn."""
    try:
        from app.apps.rpg.narration.game_master.direction_call import trigger

        why = trigger(result, document)
        if why:
            enqueue_game_master(session_id, revision, why)
        changes = {str(row.get("type")) for row in (result.get("turn_pipeline") or {}).get("changes") or ()
                   if isinstance(row, Mapping)}
        if "location_changed" in changes or int((document.get("state") or {}).get("turn_count") or 0) <= 1:
            fill_areas_ahead(session_id, document, revision)
    except Exception:
        logger.warning("rpg_game_master_enqueue_failed session=%s", session_id, exc_info=True)


def fill_areas_ahead(session_id: str, document: Mapping[str, Any], revision: int) -> None:
    """The larger areas next to the hero that are still open, each filled in by a job once a campaign (EV-10): on
    arriving somewhere, and at launch, so the starting area and its neighbours are under way before the first turn."""
    from app.apps.rpg.narration.game_master.area_call import open_areas

    for index, area in enumerate(open_areas(document)):
        enqueue_game_master(session_id, revision, f"fill:{area}", key=f"{JOB_TYPE}:area:{session_id}:{area}",
                            priority=AREA_HERE_PRIORITY if index == 0 and area == _here_area(document)
                            else AREA_PRIORITY)


def fill_areas_at_launch(session_id: str) -> None:
    """A campaign just launched: its starting area and the neighbours, filled in ahead; never fails the launch."""
    try:
        from app.apps.rpg.foundation.state import access as sections
        from app.apps.rpg.session.persistence.session_records import load_session_from_postgres

        document = load_session_from_postgres(session_id) if session_id else None
        if document:
            revision = int((sections.runtime_state_of(document) or {}).get("state_revision") or 0)
            fill_areas_ahead(session_id, document, revision)
    except Exception:
        logger.warning("rpg_game_master_launch_fill_failed session=%s", session_id, exc_info=True)


def _here_area(document: Mapping[str, Any]) -> str:
    from app.apps.rpg.foundation.state import access as sections
    from app.apps.rpg.rules.routines import hero_location

    simulation = sections.simulation_state_of(document) or {}
    place = ((sections.world_model_of(simulation) or {}).get("locations") or {}).get(hero_location(simulation)) or {}
    return str(place.get("region_id") or "") if isinstance(place, Mapping) else ""


def execute_game_master_job(job_store: Any, job: JobRecord) -> JobRecord:
    from app.apps.rpg.narration.game_master.direction_call import direct
    from app.apps.rpg.session.persistence.session_records import load_session_from_postgres

    request = RpgGameMasterJobInput.model_validate(job.input_payload or {})
    attempt = max(1, int(getattr(job, "_attempt_count", 0) or 1))
    job_store.mark_running(job.id)
    try:
        document = load_session_from_postgres(request.session_id) or {}
        if document and request.why.startswith("fill:"):
            from app.apps.rpg.narration.game_master.area_call import fill_area

            report = fill_area(request.session_id, document, request.why.removeprefix("fill:"), revision=request.revision)
            if report.get("reason") == "the model failed":  # an area is filled once a campaign: try again
                raise RuntimeError("the game master's area fill failed")
        else:
            report = direct(request.session_id, document, request.why, revision=request.revision) if document else {}
    except Exception as exc:
        failed = job_store.fail_job(job.id, FailJobRequest(
            code="rpg_game_master_failed", message=str(exc) or "the game master's direction failed",
            retryable=attempt < MAX_ATTEMPTS, details={"session_id": request.session_id, "attempt": attempt}))
        return failed or job
    completed = job_store.complete_job(job.id, CompleteJobRequest(output_refs=[{
        "type": "rpg_game_master", "module": "rpg", "session_id": request.session_id,
        "proposed": int(report.get("proposed") or 0), "dropped": list(report.get("dropped") or ())}]))
    return completed or job


__all__ = ["JOB_TYPE", "RpgGameMasterJobInput", "after_commit", "enqueue_game_master", "execute_game_master_job",
           "fill_areas_ahead", "fill_areas_at_launch"]
