from __future__ import annotations

from typing import Any, Dict, Iterable

# Generated split module for app.rpg.session.runtime.
# Phase 8.35: when the semantic classifier has already produced a complete
# stateless player-facing response, use it as the canonical visible narration and
# do not spend another blocking LLM call asking the full narrator to rephrase it.
from .runtime_part34 import *  # noqa: F401,F403
from .runtime_part33 import _apply_turn_authoritative as _PHASE8_PART35_BASE_APPLY_TURN_AUTHORITATIVE
from . import runtime_part04 as _part04
from . import runtime_part31 as _part31

_PHASE8_PART35_SOURCE = "semantic_classifier_visible_response"
_PHASE8_PART35_ORIGINAL_COMPILE_SEMANTIC_ACTION_RECORD = _part04._compile_semantic_action_record


def _phase8_part35_iter_dicts(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _phase8_part35_iter_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _phase8_part35_iter_dicts(child)


def _phase8_part35_clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    return "" if text.casefold() in {"", "[]", "{}", "null", "none"} else text


def _phase8_part35_bool_false(value: Any) -> bool:
    if value is False:
        return True
    if isinstance(value, str):
        return value.strip().casefold() in {"false", "no", "0"}
    if isinstance(value, int):
        return value == 0
    return False


def _phase8_part35_semantic_visible_candidate(source: Dict[str, Any]) -> Dict[str, Any]:
    source = _safe_dict(source)
    visible = _safe_dict(source.get("visible_response"))
    if not visible:
        return {}
    if not _phase8_part35_bool_false(source.get("stateful")):
        return {}
    if not _phase8_part35_bool_false(source.get("needs_runtime_resolution")):
        return {}

    narration = _phase8_part35_clean_text(visible.get("narration") or visible.get("text"))
    npc = _safe_dict(visible.get("npc"))
    npc_line = _phase8_part35_clean_text(npc.get("line") or npc.get("text"))
    if not narration and not npc_line:
        return {}

    speaker = _phase8_part35_clean_text(
        npc.get("speaker")
        or npc.get("name")
        or source.get("target_name")
        or ""
    )
    if npc_line and speaker:
        final = f"{narration}\n\n{speaker}: \"{npc_line}\"" if narration else f"{speaker}: \"{npc_line}\""
    elif npc_line:
        final = f"NPC: \"{npc_line}\""
    else:
        final = narration

    return {
        "narration": final,
        "final_narration": final,
        "raw_payload_narration": final,
        "deterministic_fallback_narration": final,
        "narration_status": "completed",
        "used_llm": True,
        "llm_called": True,
        "llm_purpose": "semantic_visible_response",
        "semantic_visible_response": visible,
        "semantic_action_classification": source,
        "narration_json": {
            "format_version": "semantic_visible_response_v1",
            "narration": narration,
            "action": _safe_str(source.get("activity_label") or source.get("action_type")),
            "npc": {"speaker": speaker, "line": npc_line} if (speaker or npc_line) else None,
            "semantic_family": _safe_str(source.get("semantic_family")),
            "interaction_mode": _safe_str(source.get("interaction_mode")),
        },
        "npc": {"speaker": speaker, "line": npc_line} if (speaker or npc_line) else {},
        "fallback_narration_source": _PHASE8_PART35_SOURCE,
        "skip_full_structured_narrator": True,
    }


def _phase8_part35_semantic_visible_response_fields(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = _safe_dict(payload)
    for source in _phase8_part35_iter_dicts(payload):
        fields = _phase8_part35_semantic_visible_candidate(source)
        if fields:
            return fields
    return {}


def _phase8_part35_existing_completed_semantic_or_llm_narration(payload: Dict[str, Any]) -> str:
    semantic_fields = _phase8_part35_semantic_visible_response_fields(payload)
    if semantic_fields:
        return _safe_str(semantic_fields.get("final_narration") or semantic_fields.get("narration"))
    try:
        return _phase8_part34_existing_completed_llm_narration(payload)
    except Exception:
        return ""


def _phase8_part31_existing_completed_narration(payload: Dict[str, Any]) -> str:
    return _phase8_part35_existing_completed_semantic_or_llm_narration(payload)


def _phase8_part31_should_sync_narration(payload: Dict[str, Any]) -> bool:
    if _phase8_part35_semantic_visible_response_fields(payload):
        return False
    # Preserve runtime_part31's original policy for all other turns.  It will use
    # the patched _phase8_part31_existing_completed_narration above, so real LLM
    # narration still suppresses redundant narrator calls while deterministic
    # fallback text does not.
    request = _phase8_part31_narration_request(payload)
    if not request:
        return False
    perf = _safe_dict(request.get("performance"))
    if perf.get("enable_live_narration_llm") is False:
        return False
    if _phase8_part31_existing_completed_narration(payload):
        return False
    scene = _safe_dict(request.get("scene"))
    context = _safe_dict(request.get("narration_context"))
    return bool(scene or context)


def _compile_semantic_action_record(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    player_input: str,
    action: Dict[str, Any],
    semantic_advisory: Dict[str, Any],
) -> Dict[str, Any]:
    record = _safe_dict(
        _PHASE8_PART35_ORIGINAL_COMPILE_SEMANTIC_ACTION_RECORD(
            simulation_state,
            runtime_state,
            player_input,
            action,
            semantic_advisory,
        )
    )
    advisory = _safe_dict(semantic_advisory)
    visible = _safe_dict(advisory.get("visible_response"))
    if visible:
        record["visible_response"] = visible
        record["semantic_visible_response"] = visible
    if "stateful" in advisory:
        record["stateful"] = bool(advisory.get("stateful"))
    if "needs_runtime_resolution" in advisory:
        record["needs_runtime_resolution"] = bool(advisory.get("needs_runtime_resolution"))
    for key in ("semantic_family", "interaction_mode", "activity_label", "target_id", "target_name", "action_type"):
        if _safe_str(advisory.get(key)) and not _safe_str(record.get(key)):
            record[key] = advisory.get(key)
    return record


def _phase8_part35_patch_semantic_visible_response(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    fields = _phase8_part35_semantic_visible_response_fields(payload)
    if not fields:
        return payload

    patched = dict(payload)
    for key, value in fields.items():
        if key == "npc" and not value:
            continue
        patched[key] = value

    for nested_key in ("result", "authoritative", "payload"):
        nested = _safe_dict(patched.get(nested_key))
        if not nested:
            continue
        nested = dict(nested)
        for key, value in fields.items():
            if key == "npc" and not value:
                continue
            nested[key] = value
        patched[nested_key] = nested

    if not _safe_dict(patched.get("result")):
        patched["result"] = {key: value for key, value in patched.items() if key != "authoritative"}
    if not _safe_dict(patched.get("authoritative")):
        patched["authoritative"] = dict(_safe_dict(patched.get("result")))
    return patched


def _apply_turn_authoritative(
    session_id: str,
    player_input: str,
    action: Dict[str, Any] | None = None,
    *,
    performance_override: Dict[str, Any] | None = None,
    _base_authoritative: Any = _PHASE8_PART35_BASE_APPLY_TURN_AUTHORITATIVE,
) -> Dict[str, Any]:
    payload = _base_authoritative(
        session_id,
        player_input,
        action,
        performance_override=performance_override,
    )
    return _phase8_part35_patch_semantic_visible_response(payload)


# Patch split modules whose functions resolve these names from their own globals.
_part04._compile_semantic_action_record = _compile_semantic_action_record
_part31._phase8_part31_existing_completed_narration = _phase8_part31_existing_completed_narration
_part31._phase8_part31_should_sync_narration = _phase8_part31_should_sync_narration

__all__ = [name for name in globals() if not name.startswith("__")]
