"""The lifecycle of a committed interaction: recorded by the turn's commit, its narration's outcome reported (not
saved: the campaign is saved only by a turn's commit, roadmap §4.1)."""
from __future__ import annotations

from app.runtime.clock import utc_now

from copy import deepcopy
from typing import Any

INTERACTION_LIFECYCLE_VERSION = "rpg_interaction_lifecycle_v1"


def initialize_interaction_lifecycle(
    session: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    """Attach one lifecycle record to an already committed interaction."""

    interaction_id = _text(result.get("interaction_id"))
    if not interaction_id:
        return {}
    turn_id = _first_text(result, "turn_id")
    stateful = _first_bool(result, "stateful")
    record = {
        "format_version": INTERACTION_LIFECYCLE_VERSION,
        "interaction_id": interaction_id,
        "turn_id": turn_id,
        "submission_id": _text(result.get("submission_id")),
        "stateful": stateful,
        "status": "runtime_resolved",
        "accepted_at": _utc_now(),
        "runtime_resolved_at": _utc_now(),
        "narration_status": "not_requested",
        "authoritative_response": _compact_authoritative_response(result),
        "updated_at": _utc_now(),
    }
    from app.apps.rpg.foundation.state.changes import LifecycleRecorded
    from app.apps.rpg.foundation.state.reducer import reduce

    # The commit owns the session: the reducer records the lifecycle, and its timeline event, in place.
    reduce(session, [LifecycleRecorded(interaction_id=interaction_id, turn_id=turn_id, lifecycle=record)], owned=True)
    result["interaction_lifecycle"] = deepcopy(record)
    result["narration_status"] = record["narration_status"]
    return record


def _compact_authoritative_response(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "turn_id": _first_text(result, "turn_id"),
            "tick": _first_value(result, "tick"),
            "action_type": _first_text(result, "action_type", "semantic_action_type"),
            "outcome": _first_text(result, "outcome"),
            "narration": _first_text(result, "final_narration", "narration", "summary"),
        }.items()
        if value not in (None, "")
    }


def _first_text(result: dict[str, Any], *keys: str) -> str:
    value = _first_value(result, *keys)
    return _text(value)


def _first_value(result: dict[str, Any], *keys: str) -> Any:
    for source in (result, _dict(result.get("result")), _dict(result.get("authoritative"))):
        for key in keys:
            value = source.get(key)
            if value is not None and value != "":
                return value
    return None


def _first_bool(result: dict[str, Any], key: str) -> bool | None:
    value = _first_value(result, key)
    return value if isinstance(value, bool) else None


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _utc_now() -> str:
    return utc_now().isoformat()
