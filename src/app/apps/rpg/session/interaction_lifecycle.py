"""The lifecycle of a committed interaction: recorded by the turn's commit, its narration's outcome reported (not
saved: the campaign is saved only by a turn's commit, roadmap §4.1)."""
from __future__ import annotations

from app.runtime.clock import utc_now

from copy import deepcopy
from typing import Any
from app.apps.rpg.foundation.state import access as _sections

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


def apply_narration_result_to_interaction(
    session_id: str,
    worker_result: dict[str, Any],
) -> dict[str, Any]:
    """The narration's outcome for the turn's interaction (a narration recovered from a save made before WP-5.6).

    It is told on the narration event log and kept by its job; nothing is saved here (one save per turn, by its
    commit), so the campaign keeps the lifecycle its commit recorded."""

    from app.apps.rpg.session.session_runtime_store import load_runtime_session

    session = load_runtime_session(session_id)
    if not isinstance(session, dict):
        return worker_result
    runtime = _dict(_sections.runtime_state_of(session))
    turn_id = _text(worker_result.get("turn_id"))
    interaction_id = _text(worker_result.get("interaction_id")) or _text(
        _dict(runtime.get("interaction_id_by_turn")).get(turn_id)
    )
    if not interaction_id:
        return worker_result
    lifecycles = _dict(runtime.get("interaction_lifecycles"))
    current = _dict(lifecycles.get(interaction_id))
    if not current or (current.get("turn_id") and _text(current.get("turn_id")) != turn_id):
        return worker_result

    status = _text(worker_result.get("status")).lower()
    if status == "completed":
        lifecycle_status = "narration_complete"
        narration_status = "complete"
    elif status == "failed":
        lifecycle_status = "narration_failed"
        narration_status = "failed"
    elif status in {"queued", "processing"}:
        lifecycle_status = "narration_pending"
        narration_status = status
    else:
        return worker_result

    updated = {
        **current,
        "status": lifecycle_status,
        "narration_status": narration_status,
        "updated_at": _utc_now(),
    }
    if lifecycle_status == "narration_complete":
        artifact = _dict(worker_result.get("artifact"))
        updated["narration_complete_at"] = _utc_now()
        updated["narration_enrichment"] = _compact_narration_artifact(artifact)
    elif lifecycle_status == "narration_failed":
        updated["narration_failed_at"] = _utc_now()
        updated["narration_error"] = _text(worker_result.get("error")) or "narration_failed"
    else:
        updated["narration_pending_at"] = current.get("narration_pending_at") or _utc_now()

    worker_result = dict(worker_result)
    worker_result["interaction_id"] = interaction_id
    worker_result["interaction_lifecycle"] = deepcopy(updated)
    return worker_result


def recover_pending_interaction_narration(session_id: str, session: dict[str, Any]) -> int:
    runtime = _dict(_sections.runtime_state_of(session))
    lifecycles = _dict(runtime.get("interaction_lifecycles"))
    pending = [
        lifecycle
        for lifecycle in lifecycles.values()
        if isinstance(lifecycle, dict) and lifecycle.get("status") == "narration_pending"
    ]
    if not pending:
        return 0
    # Saves from before WP-5.6 kept the request in the session's narration
    # queue; give each pending one its rpg.narration job (idempotent). Newer
    # pending narration already has its job, and its session holds no queue.
    legacy_queue = _dict(runtime.get("narration_jobs_by_turn"))
    recovered = 0
    for lifecycle in pending:
        turn_id = _text(lifecycle.get("turn_id"))
        request = _dict(_dict(legacy_queue.get(turn_id)).get("narration_request"))
        if not turn_id or not request:
            continue
        from app.apps.rpg.session.jobs.narration_job import enqueue_rpg_narration

        enqueue_rpg_narration(
            session_id,
            turn_id,
            {**request, "session_id": session_id},
            interaction_id=_text(lifecycle.get("interaction_id")),
            tick=int(request.get("tick") or 0),
        )
        recovered += 1
    return recovered


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


def _compact_narration_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "artifact_type": _text(artifact.get("artifact_type")),
            "turn_id": _text(artifact.get("turn_id")),
            "tick": artifact.get("tick"),
            "narration": _text(artifact.get("narration"))[:4000],
            "narration_json": _dict(artifact.get("narration_json")),
            "used_llm": bool(artifact.get("used_llm")),
            "created_at": _text(artifact.get("created_at")),
        }.items()
        if value not in (None, "", {})
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
