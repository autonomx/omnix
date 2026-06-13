from __future__ import annotations

from typing import Any, Dict

# Generated split module for app.rpg.session.runtime.
# Phase 8.33: the streaming route builds its authoritative_result payload from
# nested result/authoritative dicts.  Phase 8.31 can place the synchronous LLM
# narration on the top-level payload, so mirror completed visible narration into
# the nested payloads before the route extracts fallback_narration.
from .runtime_part32 import *  # noqa: F401,F403
from .runtime_part31 import _apply_turn_authoritative as _PHASE8_PART33_BASE_APPLY_TURN_AUTHORITATIVE

_PHASE8_PART33_SOURCE = "phase8_sync_narration_stream_payload_mirror"
_PHASE8_PART33_VISIBLE_KEYS = (
    "narration",
    "final_narration",
    "raw_payload_narration",
    "deterministic_fallback_narration",
    "narration_status",
    "used_llm",
    "raw_llm_narrative",
    "narration_json",
    "npc",
    "grounding_validation",
    "grounding_fallback",
    "fallback_narration_source",
)


def _phase8_part33_has_visible_text(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        text = value.strip()
        return bool(text and text.casefold() not in {"[]", "{}", "null", "none"})
    if isinstance(value, (dict, list, tuple, set)):
        return bool(value)
    return True


def _phase8_part33_completed_visible_fields(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = _safe_dict(payload)
    status = _safe_str(payload.get("narration_status")).strip().casefold()
    text = _safe_str(
        payload.get("final_narration")
        or payload.get("narration")
        or payload.get("raw_payload_narration")
        or payload.get("deterministic_fallback_narration")
    ).strip()
    if not text:
        return {}

    fields: Dict[str, Any] = {}
    for key in _PHASE8_PART33_VISIBLE_KEYS:
        value = payload.get(key)
        if _phase8_part33_has_visible_text(value):
            fields[key] = value

    fields.setdefault("narration", text)
    fields.setdefault("final_narration", text)
    fields["deterministic_fallback_narration"] = text
    fields["narration_status"] = "completed" if status == "completed" else (status or "completed")
    fields["fallback_narration_source"] = _PHASE8_PART33_SOURCE
    return fields


def _phase8_part33_mirror_visible_fields(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = _safe_dict(payload)
    if not payload:
        return payload

    fields = _phase8_part33_completed_visible_fields(payload)
    if not fields:
        return payload

    patched = dict(payload)
    for key, value in fields.items():
        patched[key] = value

    for nested_key in ("result", "authoritative", "payload"):
        nested = _safe_dict(patched.get(nested_key))
        if not nested:
            continue
        nested = dict(nested)
        for key, value in fields.items():
            nested[key] = value
        patched[nested_key] = nested

    # If this runtime path does not expose nested dictionaries, create the two
    # shapes consumed by _stream_authoritative_payload so the route cannot fall
    # back to an older action/result echo.
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
    _base_authoritative: Any = _PHASE8_PART33_BASE_APPLY_TURN_AUTHORITATIVE,
) -> Dict[str, Any]:
    payload = _base_authoritative(
        session_id,
        player_input,
        action,
        performance_override=performance_override,
    )
    return _phase8_part33_mirror_visible_fields(payload)


__all__ = [name for name in globals() if not name.startswith("__")]
