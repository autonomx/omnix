"""A turn queued as an ``rpg.turn`` job (the workspace's turn request): the turn route's own steps (RQ-2.10).

The job names its campaign (``input_ref.session_id``) and the player's words (``input_payload.command``); it runs
through ``submit_rpg_turn`` keyed by the job, like a Hermes turn, so it is committed, narrated and answered as the
play screen's turn is. The job's output is the turn's visible text. A job with no campaign, or a turn the route
refuses, fails the job with the route's reason; only a turn waiting on another of the campaign's is retried.
"""
from __future__ import annotations

from typing import Any

from app.jobs.handlers import JobFailure, JobResult, JobRun, PermanentJobError
from app.jobs.inline_execution import require_execution_authority
from app.jobs.models import JobRecord

_RETRYABLE = frozenset({"rpg_turn_in_progress", "rpg_state_revision_conflict", "rpg_turn_budget_exceeded"})


def run_rpg_turn_job(run: JobRun[Any]) -> JobResult:
    """Execute one leased RPG turn through the turn route's steps."""
    job = run.job
    if job.type != "rpg.turn":
        raise PermanentJobError("unsupported_rpg_job_type", f"Unsupported RPG job type: {job.type}")
    command, visible = _run_turn(run.store, job)
    return JobResult(
        output_refs=({"type": "rpg_turn_response", "module": job.module, "title": command[:80] or "RPG turn",
                      "content": visible},),
        logs=({"level": "info", "message": "RPG turn applied through the turn route", "content": visible},),
    )


def _run_turn(job_store: Any, job: JobRecord) -> tuple[str, str]:
    from app.apps.rpg.edge.api.turn_pipeline import submit_rpg_turn

    payload = job.input_payload or {}
    command = str(payload.get("command") or "").strip()
    session_id = str((job.input_ref or {}).get("session_id") or "").strip() if isinstance(job.input_ref, dict) else ""
    if not command:
        raise PermanentJobError("rpg_command_required", "RPG command is required")
    if not session_id:
        raise PermanentJobError("rpg_session_required", "An RPG turn names its campaign (input_ref.session_id)")
    require_execution_authority(job_store, job.id)
    answer = submit_rpg_turn(session_id=session_id, command=command, submission_id=f"job:{job.id}",
                             source="rpg.turn_job")
    if answer.get("ok") is not True:
        code = str(answer.get("error") or "rpg_turn_refused")
        raise JobFailure(code, str(answer.get("message") or code), retryable=code in _RETRYABLE)
    visible = raw_visible_response if isinstance(raw_visible_response := answer.get("visible_response"), dict) else {}
    text = str(visible.get("plain_text") or visible.get("narration") or "").strip()
    if not text:
        raise PermanentJobError("rpg_turn_without_visible_response", "The turn produced no visible response")
    return command, text


__all__ = ["run_rpg_turn_job"]
