from __future__ import annotations

import hashlib
from typing import Any, Dict, Iterable, List

# Generated split module for app.rpg.session.runtime.
# Phase 8.36: semantic visible responses are prompt/turn scoped.  The previous
# Phase 8.35 promotion scanned the entire authoritative payload recursively, so
# a historical semantic visible_response embedded in runtime state could be
# mistaken for the current turn's answer.  This module only promotes classifier
# visible_response objects that match the current turn id/tick/player input.
from .runtime_part35 import *  # noqa: F401,F403
from . import runtime_part04 as _part04
from . import runtime_part35 as _part35

_PHASE8_PART36_SOURCE = "phase8_current_turn_bound_semantic_visible_response"
_PHASE8_PART36_ORIGINAL_COMPILE_SEMANTIC_ACTION_RECORD = _part04._compile_semantic_action_record
_PHASE8_PART36_ORIGINAL_PERSIST_SEMANTIC_ARTIFACT = _part35._phase8_part35_persist_semantic_artifact


def _phase8_part36_norm(value: Any) -> str:
    return " ".join(_safe_str(value).strip().casefold().split())


def _phase8_part36_hash_text(value: Any) -> str:
    text = _phase8_part36_norm(value)
    if not text:
        return ""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def _phase8_part36_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _phase8_part36_shallow_sources(payload: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    payload = _safe_dict(payload)
    if not payload:
        return
    roots: List[Dict[str, Any]] = [payload]
    for key in ("result", "authoritative", "payload"):
        nested = _safe_dict(payload.get(key))
        if nested:
            roots.append(nested)

    semantic_keys = (
        "action",
        "semantic_action",
        "semantic_action_record",
        "semantic_advisory",
        "resolved_result",
        "current_action_response",
    )
    seen: set[int] = set()
    for root in roots:
        sid = id(root)
        if sid not in seen:
            seen.add(sid)
            yield root
        for key in semantic_keys:
            value = root.get(key)
            if isinstance(value, dict):
                sid = id(value)
                if sid not in seen:
                    seen.add(sid)
                    yield value
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        sid = id(item)
                        if sid not in seen:
                            seen.add(sid)
                            yield item

        # Runtime state may contain the current semantic action record alongside
        # older records.  Do not recurse blindly; the caller filters these by
        # exact turn identity before accepting a visible response.
        runtime_state = _safe_dict(root.get("runtime_state"))
        for key in ("semantic_action_records", "llm_records", "narration_artifacts"):
            for item in _safe_list(runtime_state.get(key)):
                if isinstance(item, dict):
                    sid = id(item)
                    if sid not in seen:
                        seen.add(sid)
                        yield item
        for mapping_key in ("semantic_action_index", "narration_artifacts_by_turn"):
            for item in _safe_dict(runtime_state.get(mapping_key)).values():
                if isinstance(item, dict):
                    sid = id(item)
                    if sid not in seen:
                        seen.add(sid)
                        yield item


def _phase8_part36_current_identity(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = _safe_dict(payload)
    turn_id = ""
    tick = 0
    player_input = ""
    player_input_hash = ""
    for source in _phase8_part35_iter_dicts(payload):
        if not turn_id:
            turn_id = _safe_str(source.get("turn_id")).strip()
        if not tick:
            tick = _phase8_part36_int(source.get("tick"))
        if not player_input:
            player_input = _safe_str(
                source.get("player_input")
                or source.get("input")
                or source.get("raw_player_input")
            ).strip()
        if not player_input_hash:
            player_input_hash = _safe_str(source.get("player_input_hash")).strip()
        if turn_id and tick and (player_input or player_input_hash):
            break
    if not player_input_hash:
        player_input_hash = _phase8_part36_hash_text(player_input)
    return {
        "turn_id": turn_id,
        "tick": tick,
        "player_input": player_input,
        "player_input_hash": player_input_hash,
    }


def _phase8_part36_source_identity(source: Dict[str, Any]) -> Dict[str, Any]:
    source = _safe_dict(source)
    player_input = _safe_str(
        source.get("player_input")
        or source.get("input")
        or source.get("raw_player_input")
    ).strip()
    player_input_hash = _safe_str(source.get("player_input_hash")).strip()
    if not player_input_hash:
        player_input_hash = _phase8_part36_hash_text(player_input)
    return {
        "turn_id": _safe_str(source.get("turn_id")).strip(),
        "tick": _phase8_part36_int(source.get("tick")),
        "player_input": player_input,
        "player_input_hash": player_input_hash,
    }


def _phase8_part36_identity_matches(current: Dict[str, Any], source: Dict[str, Any]) -> bool:
    current = _safe_dict(current)
    source_id = _phase8_part36_source_identity(source)

    current_turn_id = _safe_str(current.get("turn_id")).strip()
    source_turn_id = _safe_str(source_id.get("turn_id")).strip()
    if source_turn_id and current_turn_id and source_turn_id != current_turn_id:
        return False

    current_tick = _phase8_part36_int(current.get("tick"))
    source_tick = _phase8_part36_int(source_id.get("tick"))
    if source_tick and current_tick and source_tick != current_tick:
        return False

    current_hash = _safe_str(current.get("player_input_hash")).strip()
    source_hash = _safe_str(source_id.get("player_input_hash")).strip()
    if source_hash and current_hash and source_hash != current_hash:
        return False

    current_input = _phase8_part36_norm(current.get("player_input"))
    source_input = _phase8_part36_norm(source_id.get("player_input"))
    if source_input and current_input and source_input != current_input:
        return False

    return True


def _phase8_part35_semantic_visible_response_fields(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = _safe_dict(payload)
    current = _phase8_part36_current_identity(payload)
    for source in _phase8_part36_shallow_sources(payload):
        if not _phase8_part36_identity_matches(current, source):
            continue
        fields = _phase8_part35_semantic_visible_candidate(source)
        if not fields:
            continue
        fields = dict(fields)
        fields["fallback_narration_source"] = _PHASE8_PART36_SOURCE
        fields["turn_binding"] = dict(current)
        narration_json = _safe_dict(fields.get("narration_json"))
        narration_json["turn_binding"] = dict(current)
        fields["narration_json"] = narration_json
        return fields
    return {}


def _compile_semantic_action_record(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    player_input: str,
    action: Dict[str, Any],
    semantic_advisory: Dict[str, Any],
) -> Dict[str, Any]:
    record = _safe_dict(
        _PHASE8_PART36_ORIGINAL_COMPILE_SEMANTIC_ACTION_RECORD(
            simulation_state,
            runtime_state,
            player_input,
            action,
            semantic_advisory,
        )
    )
    player_input_clean = _safe_str(record.get("player_input") or player_input).strip()
    if player_input_clean:
        record["player_input"] = player_input_clean
        record["player_input_hash"] = _phase8_part36_hash_text(player_input_clean)
    if not _safe_str(record.get("turn_id")).strip():
        tick = _phase8_part36_int(record.get("tick"))
        if tick:
            record["turn_id"] = f"turn:{tick}"
    record["semantic_response_binding"] = {
        "turn_id": _safe_str(record.get("turn_id")),
        "tick": _phase8_part36_int(record.get("tick")),
        "player_input_hash": _safe_str(record.get("player_input_hash")),
    }
    return record


def _phase8_part35_persist_semantic_artifact(session_id: str, payload: Dict[str, Any], fields: Dict[str, Any]) -> None:
    fields = _safe_dict(fields)
    binding = _safe_dict(fields.get("turn_binding")) or _phase8_part36_current_identity(payload)
    turn_id = _safe_str(binding.get("turn_id")).strip() or _phase8_part35_payload_turn_id(payload)
    if not turn_id:
        return
    payload = dict(_safe_dict(payload))
    payload["turn_id"] = turn_id
    if binding.get("tick"):
        payload["tick"] = _phase8_part36_int(binding.get("tick"))
    fields = dict(fields)
    fields["turn_binding"] = binding
    _PHASE8_PART36_ORIGINAL_PERSIST_SEMANTIC_ARTIFACT(session_id, payload, fields)


# Patch split modules whose functions resolve these helpers from module globals.
_part04._compile_semantic_action_record = _compile_semantic_action_record
_part35._phase8_part35_semantic_visible_response_fields = _phase8_part35_semantic_visible_response_fields
_part35._compile_semantic_action_record = _compile_semantic_action_record
_part35._phase8_part35_persist_semantic_artifact = _phase8_part35_persist_semantic_artifact

__all__ = [name for name in globals() if not name.startswith("__")]
