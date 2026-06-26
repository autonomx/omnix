"""P0 guards for RPG turn job latency and duplicate visible output."""
from __future__ import annotations

import re
from functools import wraps
from typing import Any, Callable

from .models import JobRecord, JobStatus

_RPG_TURN_JOB_TYPE = "rpg.turn"
_ACTIVE_DUPLICATE_STATUSES = {
    JobStatus.QUEUED,
    JobStatus.LEASED,
    JobStatus.RUNNING,
    JobStatus.WAITING,
    JobStatus.RETRYING,
}


def install_rpg_turn_job_guard(sqlite_job_store_cls: Any) -> None:
    """Prevent duplicate active RPG turn jobs and duplicate visible speaker text."""

    if not getattr(sqlite_job_store_cls, "_omnix_rpg_turn_job_guard_installed", False):
        original_create_job: Callable[..., JobRecord] = sqlite_job_store_cls.create_job

        @wraps(original_create_job)
        def create_job_with_rpg_turn_guard(self: Any, request: Any) -> JobRecord:
            duplicate = _find_active_duplicate_rpg_turn_job(self, request)
            if duplicate is not None:
                return duplicate
            return original_create_job(self, request)

        sqlite_job_store_cls.create_job = create_job_with_rpg_turn_guard
        sqlite_job_store_cls._omnix_rpg_turn_job_guard_installed = True

    _patch_rpg_turn_visible_formatter()


def _find_active_duplicate_rpg_turn_job(job_store: Any, request: Any) -> JobRecord | None:
    if _text(getattr(request, "type", "")) != _RPG_TURN_JOB_TYPE:
        return None
    payload = _dict_value(getattr(request, "input_payload", None))
    input_ref = _dict_value(getattr(request, "input_ref", None))
    command = _text(payload.get("command"))
    session_id = _text(input_ref.get("session_id"))
    if not command or not session_id:
        return None

    try:
        jobs = job_store.list_jobs()
    except Exception:
        return None

    for job in jobs:
        if job.type != _RPG_TURN_JOB_TYPE:
            continue
        if job.status not in _ACTIVE_DUPLICATE_STATUSES:
            continue
        job_payload = _dict_value(job.input_payload)
        job_ref = _dict_value(job.input_ref)
        if _text(job_payload.get("command")) == command and _text(job_ref.get("session_id")) == session_id:
            return job
    return None


def _patch_rpg_turn_visible_formatter() -> None:
    try:
        from . import inline_feature_jobs
    except Exception:
        return

    if getattr(inline_feature_jobs, "_omnix_rpg_turn_visible_formatter_guard_installed", False):
        return
    original = inline_feature_jobs._format_rpg_turn_first_call_visible_response

    @wraps(original)
    def guarded_formatter(*args: Any, **kwargs: Any) -> str | None:
        text = original(*args, **kwargs)
        return _collapse_duplicate_visible_paragraphs(text)

    inline_feature_jobs._format_rpg_turn_first_call_visible_response = guarded_formatter
    inline_feature_jobs._omnix_rpg_turn_visible_formatter_guard_installed = True


def _collapse_duplicate_visible_paragraphs(text: str | None) -> str | None:
    if not text:
        return text
    out: list[str] = []
    seen: set[str] = set()
    for part in str(text).split("\n\n"):
        paragraph = part.strip()
        if not paragraph:
            continue
        key = _visible_key(paragraph)
        if key and key in seen:
            continue
        seen.add(key)
        out.append(paragraph)
    return "\n\n".join(out) or None


def _visible_key(text: str) -> str:
    normalized = _text(text).casefold().strip()
    # Treat `Bran: text` and `Bran: "text"` as the same paragraph.
    normalized = re.sub(r":\s*[\"“”'`]+", ": ", normalized)
    normalized = re.sub(r"[\"“”'`]", "", normalized)
    normalized = re.sub(r"[^a-z0-9:]+", " ", normalized)
    return normalized.strip()


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""
