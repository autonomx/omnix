"""Exactly-once guards for foreground RPG turns and durable job transitions."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from .models import JobRecord, JobStatus, TERMINAL_STATUSES

RPG_TURN_JOB_TYPE = "rpg.turn"
RPG_FOREGROUND_RECORD_TYPE = "rpg.turn.foreground_record"
_ACTIVE_DUPLICATE_STATUSES = {
    JobStatus.QUEUED,
    JobStatus.LEASED,
    JobStatus.RUNNING,
    JobStatus.WAITING,
    JobStatus.RETRYING,
}
_TERMINAL_GUARDED_METHODS = (
    "mark_running",
    "update_progress",
    "complete_job",
    "fail_job",
)


def install_rpg_turn_job_guard(sqlite_job_store_cls: Any) -> None:
    """Install idempotency and terminal-state guards without changing job APIs."""

    if getattr(sqlite_job_store_cls, "_omnix_rpg_turn_job_guard_installed", False):
        return
    _install_create_guard(sqlite_job_store_cls)
    _install_terminal_guards(sqlite_job_store_cls)
    sqlite_job_store_cls._omnix_rpg_turn_job_guard_installed = True


def _install_create_guard(sqlite_job_store_cls: Any) -> None:
    original_create_job: Callable[..., JobRecord] = sqlite_job_store_cls.create_job

    @wraps(original_create_job)
    def create_job_with_rpg_turn_guard(self: Any, request: Any) -> JobRecord:
        _sanitize_foreground_record_compat(request)
        duplicate = _find_duplicate_rpg_turn_job(self, request)
        if duplicate is not None:
            return duplicate
        return original_create_job(self, request)

    sqlite_job_store_cls.create_job = create_job_with_rpg_turn_guard


def _install_terminal_guards(sqlite_job_store_cls: Any) -> None:
    for method_name in _TERMINAL_GUARDED_METHODS:
        original = getattr(sqlite_job_store_cls, method_name)

        @wraps(original)
        def terminal_safe(
            self: Any,
            job_id: str,
            *args: Any,
            __original: Callable[..., JobRecord | None] = original,
            **kwargs: Any,
        ) -> JobRecord | None:
            existing = self.get_job(job_id)
            if existing is not None and existing.status in TERMINAL_STATUSES:
                return existing
            return __original(self, job_id, *args, **kwargs)

        setattr(sqlite_job_store_cls, method_name, terminal_safe)


def _sanitize_foreground_record_compat(request: Any) -> None:
    if _text(getattr(request, "type", "")) != RPG_FOREGROUND_RECORD_TYPE:
        return
    compat = _dict_value(getattr(request, "compat", None))
    compat.pop("synthetic_job_mirror", None)
    compat.pop("direct_foreground_route", None)
    compat["foreground_record"] = True
    compat["record_only"] = True
    try:
        request.compat = compat
    except Exception:
        pass


def _find_duplicate_rpg_turn_job(job_store: Any, request: Any) -> JobRecord | None:
    job_type = _text(getattr(request, "type", ""))
    if job_type not in {RPG_TURN_JOB_TYPE, RPG_FOREGROUND_RECORD_TYPE}:
        return None

    payload = _dict_value(getattr(request, "input_payload", None))
    input_ref = _dict_value(getattr(request, "input_ref", None))
    submission_id = _text(payload.get("submission_id"))
    command = _text(payload.get("command"))
    session_id = _text(input_ref.get("session_id"))
    if not session_id:
        return None

    try:
        jobs = job_store.list_jobs()
    except Exception:
        return None

    for job in jobs:
        if job.type != job_type:
            continue
        job_payload = _dict_value(job.input_payload)
        job_ref = _dict_value(job.input_ref)
        if _text(job_ref.get("session_id")) != session_id:
            continue
        if submission_id and _text(job_payload.get("submission_id")) == submission_id:
            return job
        if (
            job_type == RPG_TURN_JOB_TYPE
            and job.status in _ACTIVE_DUPLICATE_STATUSES
            and command
            and _text(job_payload.get("command")) == command
        ):
            return job
    return None


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""
