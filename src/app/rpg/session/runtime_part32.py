from __future__ import annotations

from typing import Any, Dict

# Generated split module for app.rpg.session.runtime.
# Phase 8.32: player-turn narration is append-only presentation for a specific
# committed turn. It must be classified separately from simulation/world-state
# artifacts before stale calculations are applied.
from .runtime_part31 import *  # noqa: F401,F403
from . import runtime_part17 as _part17

_PHASE8_PART32_ORIGINAL_GENERATE_TURN_NARRATION_ARTIFACT = _part17._generate_turn_narration_artifact
_PHASE8_PART32_SOURCE = "phase8_player_turn_late_narration_artifact_store"
_PHASE8_PART32_PLAYER_TURN_KIND = "player_turn_narration"
_PHASE8_PART32_APPEND_ONLY_POLICY = "append_only_by_turn_id"


def _phase8_part32_classify_narration_request(narration_request: Dict[str, Any]) -> Dict[str, Any]:
    """Classify narration before deciding whether tick drift makes it stale.

    The old stale check compared artifact.tick to runtime_state.tick for every
    artifact. That is correct for mutable world/simulation artifacts, but wrong
    for player-turn display narration: a valid answer for turn:N is still the
    answer for turn:N even if idle ticks advance while the model is generating.
    """

    narration_request = _safe_dict(narration_request)
    context = _safe_dict(narration_request.get("narration_context"))
    scene = _safe_dict(narration_request.get("scene"))
    turn_contract = _safe_dict(
        context.get("turn_contract")
        or narration_request.get("turn_contract")
        or scene.get("turn_contract")
    )
    explicit_kind = _safe_str(
        narration_request.get("artifact_kind")
        or narration_request.get("job_kind")
        or context.get("artifact_kind")
        or context.get("job_kind")
    ).strip().lower()

    has_player_turn_contract = bool(turn_contract)
    turn_id = _safe_str(narration_request.get("turn_id")).strip()
    is_player_turn = (
        explicit_kind in {"player_turn", "player_turn_narration", "turn_narration"}
        or (turn_id.startswith("turn:") and has_player_turn_contract)
    )

    if is_player_turn:
        return {
            "artifact_kind": _PHASE8_PART32_PLAYER_TURN_KIND,
            "staleness_policy": _PHASE8_PART32_APPEND_ONLY_POLICY,
            "is_append_only_visible_response": True,
            "stale_if_runtime_tick_advances": False,
            "source": _PHASE8_PART32_SOURCE,
        }

    return {
        "artifact_kind": explicit_kind or "background_narration",
        "staleness_policy": "runtime_tick_guarded",
        "is_append_only_visible_response": False,
        "stale_if_runtime_tick_advances": True,
        "source": _PHASE8_PART32_SOURCE,
    }


def _phase8_part32_apply_classification(
    artifact: Dict[str, Any],
    classification: Dict[str, Any],
) -> Dict[str, Any]:
    artifact = dict(_safe_dict(artifact))
    classification = _safe_dict(classification)
    if classification:
        artifact["artifact_kind"] = _safe_str(classification.get("artifact_kind"))
        artifact["staleness_policy"] = _safe_str(classification.get("staleness_policy"))
        artifact["is_append_only_visible_response"] = bool(
            classification.get("is_append_only_visible_response")
        )
        artifact["stale_if_runtime_tick_advances"] = bool(
            classification.get("stale_if_runtime_tick_advances")
        )
    return artifact


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

    # Merge only narration artifact indexes back into the live runtime. Do not
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
    narration_request = _safe_dict(narration_request)
    classification = _phase8_part32_classify_narration_request(narration_request)

    result = _PHASE8_PART32_ORIGINAL_GENERATE_TURN_NARRATION_ARTIFACT(
        session_id,
        narration_request,
        on_chunk=on_chunk,
    )
    result = _safe_dict(result)

    artifact = _safe_dict(result.get("artifact"))
    if artifact:
        artifact = _phase8_part32_apply_classification(artifact, classification)
        result["artifact"] = artifact

    if result.get("ok"):
        # Successful artifacts should still carry their category so later route
        # code can distinguish real player-turn narration from fallback text.
        session = _safe_dict(result.get("session"))
        if session and artifact and artifact.get("turn_id"):
            try:
                runtime_state = _copy_dict(session.get("runtime_state"))
                by_turn = _safe_dict(runtime_state.get("narration_artifacts_by_turn"))
                turn_id = _safe_str(artifact.get("turn_id")).strip()
                if turn_id:
                    by_turn[turn_id] = artifact
                    artifacts = [
                        artifact if _safe_str(_safe_dict(existing).get("turn_id")).strip() == turn_id else existing
                        for existing in _safe_list(runtime_state.get("narration_artifacts"))
                    ]
                    if not any(_safe_str(_safe_dict(existing).get("turn_id")).strip() == turn_id for existing in artifacts):
                        artifacts.append(artifact)
                    runtime_state["narration_artifacts"] = artifacts
                    runtime_state["narration_artifacts_by_turn"] = by_turn
                    session["runtime_state"] = runtime_state
                    result["session"] = save_runtime_session(session)
            except Exception:
                logger.exception("Failed to persist narration artifact classification")
        return result

    if _safe_str(result.get("error")) != "stale_narration_artifact":
        return result

    # Only player-turn visible narration is exempt from runtime tick staleness.
    # Background/ambient artifacts still use the original stale behavior.
    if classification.get("staleness_policy") != _PHASE8_PART32_APPEND_ONLY_POLICY:
        return result

    stored = _phase8_part32_store_late_turn_artifact(session_id, artifact)
    if stored.get("ok"):
        stored["recovered_from"] = "stale_narration_artifact"
        stored["classification"] = classification
        return stored
    return result


# process_next_narration_job is defined in runtime_part17 and resolves
# _generate_turn_narration_artifact through that module's globals at call time.
# Patch that global so the existing queue/claim/retry logic uses categorised
# stale handling without copying the whole worker implementation.
_part17._generate_turn_narration_artifact = _generate_turn_narration_artifact

__all__ = [name for name in globals() if not name.startswith("__")]
