from __future__ import annotations

from typing import Any

SOURCE = "hermes_sequence_job_contract"


def _items(state: dict[str, Any]) -> list[dict[str, Any]]:
    sequence = state.get("sequence") if isinstance(state.get("sequence"), dict) else {}
    return [dict(item) for item in sequence.get("items", []) if isinstance(item, dict)]


def hermes_sequence_job_progress(state: dict[str, Any], *, job_status: str = "queued") -> dict[str, Any]:
    items = _items(state)
    statuses = [dict(item) for item in state.get("item_statuses", []) if isinstance(item, dict)]
    done_count = sum(1 for item in statuses if item.get("status") in {"done", "completed"})
    blocked_count = sum(1 for item in statuses if item.get("status") == "blocked")
    item_count = len(items) or len(statuses)
    status = job_status
    if blocked_count:
        status = "failed" if job_status not in {"paused", "cancel_requested", "canceled"} else job_status
    elif item_count and done_count >= item_count:
        status = "completed"
    return {
        "ok": status not in {"failed", "canceled"},
        "source": SOURCE,
        "sequence_id": state.get("sequence_id"),
        "session_id": state.get("session_id"),
        "status": status,
        "current_item_index": state.get("current_item_index", 0),
        "item_count": item_count,
        "done_count": done_count,
        "blocked_count": blocked_count,
        "progress_percent": 100 if item_count == 0 else round((done_count / item_count) * 100),
        "blocked_reason": state.get("blocked_reason") or None,
    }
