"""Bounded cleanup helpers for completed job history."""
from __future__ import annotations

from typing import Any

from .models import TERMINAL_STATUSES
from .store import SQLiteJobStore


def purge_terminal_job_history(store: Any, job_id: str) -> dict[str, Any]:
    """Remove one terminal job and its event rows from a supported store."""

    normalized = str(job_id or "").strip()
    if not normalized:
        return {"ok": True, "job_id": "", "job_removed": False, "events_removed": 0}

    job = store.get_job(normalized)
    if job is None:
        return {"ok": True, "job_id": normalized, "job_removed": False, "events_removed": 0}
    if job.status not in TERMINAL_STATUSES:
        raise RuntimeError("job_not_terminal")
    if not isinstance(store, SQLiteJobStore):
        raise RuntimeError("job_store_cleanup_unsupported")

    with store._connect() as conn:  # noqa: SLF001 - bounded persistence adapter
        event_cursor = conn.execute("DELETE FROM job_events WHERE job_id = ?", (normalized,))
        job_cursor = conn.execute("DELETE FROM jobs WHERE id = ?", (normalized,))

    return {
        "ok": True,
        "job_id": normalized,
        "job_removed": bool(job_cursor.rowcount),
        "events_removed": max(0, int(event_cursor.rowcount or 0)),
    }
