"""The listener's sign-off on a production step, bound to what they approved.

Steps 3 to 5 (find speakers, cast voices, render audio) end only when the
listener approves them. An approval stores a fingerprint of the step's result
in the project settings; when that result changes (speakers found again, a
voice changed, a chapter rendered again) the fingerprint no longer matches and
the step asks for approval again. Approvals mark progress for the listener;
they do not gate rendering or export.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal, Mapping

ApprovalStep = Literal["speakers", "cast", "audio"]
APPROVAL_STEPS: tuple[ApprovalStep, ...] = ("speakers", "cast", "audio")
SETTING = "step_approvals"

_CLASSIFIED_STATES = frozenset({
    "review_required", "ready_to_render", "rendering", "mastering", "ready_to_export", "exported",
})
_ACTIVE_JOB_STATUSES = frozenset({
    "queued", "waiting", "retrying", "leased", "running", "paused", "cancel_requested",
})


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _analysis_running(project: Mapping[str, Any]) -> bool:
    return any(job.get("type") == "audiobook.analyze" and job.get("status") in _ACTIVE_JOB_STATUSES
               for job in project.get("pipeline_jobs") or [])


def approval_blocker(step: ApprovalStep, project: Mapping[str, Any]) -> str | None:
    """Why ``step`` cannot be approved yet, or ``None`` when it can."""
    if not project.get("current_source_revision_id"):
        return "Add a book first."
    if step == "speakers":
        if _analysis_running(project):
            return "Wait for Find speakers to finish."
        if project.get("state") not in _CLASSIFIED_STATES:
            return "Find speakers first."
        issues = len(project.get("review_issues") or [])
        if issues:
            return f"Confirm the speaker for {issues} line{'' if issues == 1 else 's'} first."
        return None
    if step == "cast":
        speakers = project.get("speakers") or []
        if not speakers:
            return "There are no speakers to cast yet."
        missing = sum(1 for speaker in speakers if not speaker.get("casting"))
        if missing:
            return f"Choose a voice for {missing} more speaker{'' if missing == 1 else 's'} first."
        return None
    jobs = project.get("render_jobs") or []
    if jobs:
        unfinished = sum(1 for job in jobs if job.get("status") != "completed")
        return f"Wait for {unfinished} more chapter{'' if unfinished == 1 else 's'} to render." if unfinished else None
    return None if project.get("state") in {"ready_to_export", "exported"} else "Render the book first."


def approval_basis(step: ApprovalStep, project: Mapping[str, Any], *,
                   analysis_job_id: str | None, render_run_id: str | None) -> str:
    """The fingerprint of what approving ``step`` signs off on."""
    source = str(project.get("current_source_revision_id") or "")
    if step == "speakers":
        return _fingerprint(["speakers", source, analysis_job_id or ""])
    if step == "cast":
        return _fingerprint(["cast", source, sorted(
            [str(speaker["id"]), str((speaker.get("casting") or {}).get("id") or ""),
             int((speaker.get("casting") or {}).get("revision") or 0)]
            for speaker in project.get("speakers") or []
        )])
    return _fingerprint(["audio", source, render_run_id or "", sorted(
        str(job["id"]) for job in project.get("render_jobs") or [] if job.get("status") == "completed"
    )])


def approval_status(settings: Mapping[str, Any], project: Mapping[str, Any], *,
                    analysis_job_id: str | None, render_run_id: str | None) -> dict[str, bool]:
    """Whether each step's stored approval still matches its result.

    A project rendered before approvals existed has none stored; for it, starting
    a render stands for approving speakers and cast, and exporting for the audio.
    """
    stored = settings.get(SETTING)
    stored = stored if isinstance(stored, Mapping) else {}
    implied = {
        "speakers": bool(render_run_id) or project.get("state") == "exported",
        "cast": bool(render_run_id) or project.get("state") == "exported",
        "audio": project.get("state") == "exported",
    }
    status: dict[str, bool] = {}
    for step in APPROVAL_STEPS:
        if approval_blocker(step, project) is not None:
            status[step] = False
        elif step not in stored:
            status[step] = implied[step]
        else:
            status[step] = stored[step] == approval_basis(
                step, project, analysis_job_id=analysis_job_id, render_run_id=render_run_id,
            )
    return status
