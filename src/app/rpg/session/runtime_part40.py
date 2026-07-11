from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Mapping

from app.rpg.session.response_builder import (
    build_apply_turn_response as _PHASE8_PART40_BASE_BUILD_APPLY_TURN_RESPONSE,
)

from .runtime_part19 import apply_turn as _PHASE8_PART40_BASE_APPLY_TURN
from .runtime_part39 import _canonicalize_publication, _persist_soft_truth


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def build_apply_turn_response(
    authoritative_result: Dict[str, Any],
    _base_builder: Any = _PHASE8_PART40_BASE_BUILD_APPLY_TURN_RESPONSE,
) -> Dict[str, Any]:
    """Retain the authoritative queued fallback through later presentation selection."""

    payload = _base_builder(authoritative_result)
    source = _safe_dict(authoritative_result)
    authoritative = _safe_dict(source.get("authoritative"))
    source_result = _safe_dict(source.get("result"))
    fallback = _safe_str(
        authoritative.get("deterministic_fallback_narration")
        or source_result.get("deterministic_fallback_narration")
    ).strip()
    if not fallback:
        return payload

    result = dict(_safe_dict(payload))
    nested = dict(_safe_dict(result.get("result")))
    nested["deterministic_fallback_narration"] = fallback
    result["result"] = nested
    result["deterministic_fallback_narration"] = fallback
    return result


def _queued_narration_snapshot(payload: Dict[str, Any]) -> dict[str, Any]:
    result = _safe_dict(payload)
    nested = _safe_dict(result.get("result"))
    authoritative = _safe_dict(result.get("authoritative"))
    resolved = _safe_dict(
        authoritative.get("resolved_result")
        or nested.get("resolved_result")
        or result.get("resolved_result")
    )
    status = _safe_str(
        nested.get("narration_status") or result.get("narration_status")
    ).casefold()
    narration = _safe_str(
        nested.get("deterministic_fallback_narration")
        or result.get("deterministic_fallback_narration")
        or authoritative.get("deterministic_fallback_narration")
        or resolved.get("deterministic_fallback_narration")
        or nested.get("narration")
        or result.get("narration")
    ).strip()
    if status not in {"queued", "pending"} or not narration:
        return {}
    return {
        "narration": narration,
        "narration_status": status,
        "raw_llm_narrative": _safe_str(
            nested.get("raw_llm_narrative") or result.get("raw_llm_narrative")
        ),
        "used_llm": bool(nested.get("used_llm") or result.get("used_llm")),
        "llm_called": bool(nested.get("llm_called") or result.get("llm_called")),
    }


def _restore_queued_narration(
    payload: Dict[str, Any],
    snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    if not snapshot:
        return payload
    result = dict(_safe_dict(payload))
    result["narration"] = snapshot["narration"]
    result["narration_status"] = snapshot["narration_status"]
    result["raw_llm_narrative"] = snapshot["raw_llm_narrative"]
    result["used_llm"] = snapshot["used_llm"]
    result["llm_called"] = snapshot["llm_called"]
    result["presentation_narration_selection"] = {
        "source": "canonical_deferred_fallback",
        "runtime_payload_source": "deferred_runtime_narration_pending",
    }

    narration_payload = dict(
        _safe_dict(result.get("narration_payload") or result.get("structured_narration"))
    )
    if narration_payload:
        narration_payload["narration"] = snapshot["narration"]
        narration_payload["source"] = "deferred_runtime_narration_pending"
        narration_payload["deferred"] = True
        narration_payload["narration_status"] = snapshot["narration_status"]
        result["narration_payload"] = narration_payload
        result["structured_narration"] = deepcopy(narration_payload)

    nested = dict(_safe_dict(result.get("result")))
    if nested:
        nested["narration"] = snapshot["narration"]
        nested["narration_status"] = snapshot["narration_status"]
        nested["raw_llm_narrative"] = snapshot["raw_llm_narrative"]
        nested["used_llm"] = snapshot["used_llm"]
        nested["llm_called"] = snapshot["llm_called"]
        nested["presentation_narration_selection"] = deepcopy(
            result["presentation_narration_selection"]
        )
        if narration_payload:
            nested["narration_payload"] = deepcopy(narration_payload)
            nested["structured_narration"] = deepcopy(narration_payload)
        result["result"] = nested
    return result


def apply_turn(
    session_id: str,
    player_input: str,
    action: Dict[str, Any] | None = None,
    *,
    performance_override: Dict[str, Any] | None = None,
    _base_apply_turn: Any = _PHASE8_PART40_BASE_APPLY_TURN,
) -> Dict[str, Any]:
    payload = _base_apply_turn(
        session_id,
        player_input,
        action,
        performance_override=performance_override,
    )
    queued = _queued_narration_snapshot(payload)
    canonical = _canonicalize_publication(payload, player_input=player_input)
    canonical = _restore_queued_narration(canonical, queued)
    return _persist_soft_truth(canonical, session_id)


__all__ = ["apply_turn", "build_apply_turn_response"]
