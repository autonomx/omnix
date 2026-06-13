from __future__ import annotations

from typing import Any, Dict

# Generated split module for app.rpg.session.runtime.
# Phase 8.32: player-turn narration artifacts must not be discarded simply
# because idle ticks advanced while the LLM was generating.  The artifact is
# append-only narration for a specific turn and does not overwrite newer
# simulation state, so it is safe to store even when the runtime tick has moved
# on.
from .runtime_part31 import *  # noqa: F401,F403
from . import runtime_part17 as _part17

_PHASE8_PART32_ORIGINAL_GENERATE_TURN_NARRATION_ARTIFACT = _part17._generate_turn_narration_artifact
_PHASE8_PART32_SOURCE = "phase8_player_turn_late_narration_artifact_store"


def _phase8_part32_store_late_turn_artifact(
    session_id: str,
    artifact: Dict[str, Any],
) -> Dict[str, Any]:
    artifact = _safe_dict(artifact)
    turn_id = _safe_str(artifact.get("turn_id")).strip()
    if not turn_id:
        return {"ok": False, "error": "missing_turn_id", "artifact": artifact}

    final_narration = _safe_str(artifact.get("narration")).strip()
    narration_json = _safe_dict(artifact.get("narration_json"))
    npc_line = _safe_str(_safe_dict(narration_json.get("npc")).get("line")).strip()
    if not final_narration and not npc_line:
        return {"ok": False, "error": "empty_narration_artifact", "artifact": artifact}

    session = load_runtime_session(session_id)
    if session is None:
        return {"ok": False, "error": "session_not_found_for_late_artifact", "artifact": artifact}

    runtime_state = _copy_dict(session.get("runtime_state"))
    existing = _safe_dict(_safe_dict(runtime_state.get("narration_artifacts_by_turn")).get(turn_id))
    if existing:
        return {"ok": True, "session": session, "artifact": existing, "deduped": True}

    artifact = dict(artifact)
    artifact.setdefault("late_artifact_policy", _PHASE8_PART32_SOURCE)
    updated_runtime = _store_narration_artifact(runtime_state, artifact)

    # Merge only narration artifact indexes back into the live runtime.  Do not
    # roll back ticks, simulation state, jobs, world events, or panels.
    latest_runtime = _copy_dict(session.get("runtime_state"))
    latest_runtime["narration_artifacts"] = _safe_list(updated_runtime.get("narration_artifacts"))
    latest_runtime["narration_artifacts_by_turn"] = _safe_dict(updated_runtime.get("narration_artifacts_by_turn"))
    session["runtime_state"] = latest_runtime
    session = save_runtime_session(session)

    return {"ok": True, "session": session, "artifact": artifact, "late_artifact": True}


def _generate_turn_narration_artifact(
    session_id: str,
    narration_request: Dict[str, Any],
    on_chunk: Any = None,
) -> Dict[str, Any]:
    result = _PHASE8_PART32_ORIGINAL_GENERATE_TURN_NARRATION_ARTIFACT(
        session_id,
        narration_request,
        on_chunk=on_chunk,
    )
    result = _safe_dict(result)
    if result.get("ok") or _safe_str(result.get("error")) != "stale_narration_artifact":
        return result

    # A stale player-turn narration artifact is still the correct visible AI
    # response for that turn.  Store it append-only so status polling and SSE can
    # replace the temporary queued placeholder with the real model response.
    artifact = _safe_dict(result.get("artifact"))
    stored = _phase8_part32_store_late_turn_artifact(session_id, artifact)
    if stored.get("ok"):
        stored["recovered_from"] = "stale_narration_artifact"
        return stored
    return result


# process_next_narration_job is defined in runtime_part17 and resolves
# _generate_turn_narration_artifact through that module's globals at call time.
# Patch that global so the existing queue/claim/retry logic uses the late-store
# behavior without copying the whole worker implementation.
_part17._generate_turn_narration_artifact = _generate_turn_narration_artifact

__all__ = [name for name in globals() if not name.startswith("__")]
