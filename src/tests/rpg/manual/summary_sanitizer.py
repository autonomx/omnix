"""
Summary sanitizer for manual RPG test artifacts.

Supports three detail levels:
- summary: Smallest, CI-friendly output
- debug: (default) Per-scenario debug JSON with bounded useful fields
- full: Deeper raw details but still bounded (strips pathological fields)
"""

from __future__ import annotations

import copy
import json
from typing import Any, Dict, Optional

from tests.rpg.manual.safe import _safe_dict, _safe_list, _safe_str

# ---------------------------------------------------------------------------
# Detail level constants
# ---------------------------------------------------------------------------

# Max text lengths by detail level
MAX_SUMMARY_TEXT_CHARS = 4_000
MAX_DEBUG_TEXT_CHARS = 40_000
MAX_FULL_TEXT_CHARS = 200_000

# Max list items by detail level
MAX_LIST_ITEMS_SUMMARY = 5
MAX_LIST_ITEMS_DEBUG = 25
MAX_LIST_ITEMS_FULL = 100

# Max dict keys by detail level
MAX_DICT_KEYS_SUMMARY = 20
MAX_DICT_KEYS_DEBUG = 80
MAX_DICT_KEYS_FULL = 200


# ---------------------------------------------------------------------------
# Constants for fields to always strip
# ---------------------------------------------------------------------------

# Fields to always strip from turn results in summary output
STRIP_KEYS_FROM_RESULT = {
    "session",
    "runtime_state",
    "simulation_state",
    "turn_contract",
}

# Nested keys inside result.session or result.runtime_state to cap
CAP_KEYS_IN_SESSION = {
    "turn_timings",
    "history",
    "event_history",
    "timeline",
    "conversation_thread",
    "thread",
}

# Keys to always preserve in sanitized turn output (summary level)
PRESERVE_TURN_KEYS_SUMMARY = {
    "turn_index",
    "player_input",
    "ok",
    "error",
    "llm_called",
    "llm_purpose",
    "action_type",
    "semantic_action_type",
    "visible_interaction_reason",
    "combat_narration_attempted",
    "combat_narration_accepted",
    "combat_narration_error",
    "combat_narration_validation",
    "combat_result",
    "regression_warnings",
    "scenario_warnings",
    "raw_result_keys",
    "narration_preview",
    "grounding_validation",
    "grounding_fallback",
    "grounding_selected_candidate",
    "grounding_fallback_source",
    "stateful_runtime_narration_contract",
    "stateful_runtime_check_results",
}

# Additional keys for debug level
PRESERVE_TURN_KEYS_DEBUG = PRESERVE_TURN_KEYS_SUMMARY | {
    "extracted",
    "narration_debug",
    "raw_llm_narration_capped",
    "narration_validation",
    "narration_contract",
    "combat_narration_payload",
    "turn_contract_compact",
    "resolved_result_compact",
    "structured_narration_compact",
    "narration_payload_compact",
    "grounding_primary_violations",
    "grounding_violation_codes",
    "action_type",
    "semantic_action_type",
    "compact_state_deltas",
}

# Additional keys for full level
PRESERVE_TURN_KEYS_FULL = PRESERVE_TURN_KEYS_DEBUG | {
    "result_compact",
    "full_state",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_limits(detail: str) -> Dict[str, Any]:
    """Get limits based on detail level."""
    if detail == "summary":
        return {
            "max_text": MAX_SUMMARY_TEXT_CHARS,
            "max_list": MAX_LIST_ITEMS_SUMMARY,
            "max_dict_keys": MAX_DICT_KEYS_SUMMARY,
            "strip_session": True,
            "strip_runtime_state": True,
            "strip_simulation_state": True,
            "include_extracted": False,
            "include_debug_fields": False,
            "include_full_state": False,
        }
    elif detail == "full":
        return {
            "max_text": MAX_FULL_TEXT_CHARS,
            "max_list": MAX_LIST_ITEMS_FULL,
            "max_dict_keys": MAX_DICT_KEYS_FULL,
            "strip_session": True,  # Still strip session blob
            "strip_runtime_state": False,  # Keep but cap
            "strip_simulation_state": False,  # Keep but cap
            "include_extracted": True,
            "include_debug_fields": True,
            "include_full_state": True,
        }
    else:  # debug (default)
        return {
            "max_text": MAX_DEBUG_TEXT_CHARS,
            "max_list": MAX_LIST_ITEMS_DEBUG,
            "max_dict_keys": MAX_DICT_KEYS_DEBUG,
            "strip_session": True,
            "strip_runtime_state": True,
            "strip_simulation_state": False,  # Keep compact version
            "include_extracted": True,
            "include_debug_fields": True,
            "include_full_state": False,
        }


def _preview(text: Optional[str], max_len: int) -> str:
    """Return a truncated preview of text."""
    if text is None:
        return ""
    s = _safe_str(text)
    if len(s) <= max_len:
        return s
    return s[:max_len] + f"... [truncated, {len(s)} chars total]"


def _cap_list(value: Any, max_items: int) -> Any:
    """Cap list length for summary output."""
    if isinstance(value, list):
        if len(value) <= max_items:
            return value
        return value[:max_items] + [f"... {len(value) - max_items} more items"]
    return value


def _cap_dict_keys(value: Dict[str, Any], max_keys: int) -> Dict[str, Any]:
    """Cap dict to first N keys."""
    if isinstance(value, dict):
        if len(value) <= max_keys:
            return value
        keys = list(value.keys())[:max_keys]
        capped = {k: value[k] for k in keys}
        capped["_truncated"] = f"... {len(value) - max_keys} more keys"
        return capped
    return value


def _strip_large_state(state: Optional[Dict[str, Any]], limits: Dict[str, Any]) -> Dict[str, Any]:
    """Strip large fields from a state dict."""
    if not isinstance(state, dict):
        return {}
    stripped = copy.deepcopy(state)
    max_keys = limits["max_dict_keys"]

    # Remove or cap large fields
    for key in list(stripped.keys()):
        value = stripped[key]
        if key in CAP_KEYS_IN_SESSION:
            if isinstance(value, (list, dict)):
                stripped[key] = f"[stripped: {type(value).__name__} with {len(value)} items]"
        elif key in {"inventory", "world_state", "journal", "quests", "npcs"}:
            stripped[key] = _cap_list(value, max_items=limits["max_list"])
        elif isinstance(value, dict) and len(value) > max_keys:
            stripped[key] = f"[stripped: dict with {len(value)} keys]"
        elif isinstance(value, list) and len(value) > limits["max_list"]:
            stripped[key] = f"[stripped: list with {len(value)} items]"

    return stripped


# ---------------------------------------------------------------------------
# Result compaction based on detail level
# ---------------------------------------------------------------------------

def compact_result_for_summary(
    result: Dict[str, Any],
    detail: str = "summary",
) -> Dict[str, Any]:
    """
    Compact a turn result for summary output based on detail level.

    Removes large state blobs while preserving essential diagnostic fields.
    """
    if not isinstance(result, dict):
        return result

    limits = _get_limits(detail)
    compacted: Dict[str, Any] = {}

    for key, value in result.items():
        if detail in ("debug", "full") and key == "turn_contract":
            compacted[f"{key}_compact"] = _cap_dict_keys(_safe_dict(value), limits["max_dict_keys"])
        elif key in STRIP_KEYS_FROM_RESULT:
            # Store only a marker, not the full blob
            if key == "session":
                session = _safe_dict(value)
                compacted[key] = {
                    "session_id": _safe_str(session.get("session_id")),
                    "stripped": True,
                }
            else:
                compacted[key] = f"[stripped: {key}]"
        elif key == "result" and isinstance(value, dict):
            # Recursively compact nested result
            compacted[key] = compact_result_for_summary(value, detail)
        elif key in {"authoritative", "raw_llm_narration"}:
            # Keep these but strip their large sub-fields
            compacted[key] = _strip_large_state(_safe_dict(value), limits)
        elif detail == "full" and key == "simulation_state":
            # Keep capped version for full
            compacted[key] = _strip_large_state(_safe_dict(value), limits)
        else:
            compacted[key] = value

    return compacted


# ---------------------------------------------------------------------------
# Extract useful fields for debug artifacts
# ---------------------------------------------------------------------------

def _extract_narration_preview(result: Dict[str, Any], max_len: int) -> str:
    """Extract a short narration preview from a turn result."""
    for key in ("narration", "narrative", "text", "rendered_narration"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return _preview(value.strip(), max_len)

    result_sub = _safe_dict(result.get("result"))
    for key in ("narration", "narrative", "text", "rendered_narration"):
        value = result_sub.get(key)
        if isinstance(value, str) and value.strip():
            return _preview(value.strip(), max_len)

    return ""


def _first_dict(*values: Any) -> Dict[str, Any]:
    for value in values:
        value = _safe_dict(value)
        if value:
            return value
    return {}


def _extract_result_sub(result: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(_safe_dict(result).get("result"))


def _extract_narration_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(result)
    result_sub = _extract_result_sub(result)
    session = _safe_dict(result.get("session"))
    runtime_state = _safe_dict(result.get("runtime_state"))

    return _first_dict(
        result.get("narration_payload"),
        result.get("structured_narration"),
        result.get("narration_result"),
        result.get("raw_llm_narration"),
        result.get("raw_llm_narrative"),
        result_sub.get("narration_payload"),
        result_sub.get("structured_narration"),
        result_sub.get("narration_result"),
        result_sub.get("raw_llm_narration"),
        result_sub.get("raw_llm_narrative"),
        session.get("last_narration_payload"),
        session.get("narration_payload"),
        runtime_state.get("last_narration_payload"),
        runtime_state.get("narration_payload"),
    )


def _extract_narration_json(result: Dict[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(result)
    result_sub = _extract_result_sub(result)
    payload = _extract_narration_payload(result)
    return _first_dict(
        payload.get("narration_json"),
        payload.get("structured_narration"),
        payload.get("payload"),
        payload,
        result.get("visible_response"),
        result_sub.get("visible_response"),
        result.get("first_call_visible_response"),
        result_sub.get("first_call_visible_response"),
    )


def _extract_grounding_validation(result: Dict[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(result)
    result_sub = _extract_result_sub(result)
    payload = _extract_narration_payload(result)
    narration_json = _extract_narration_json(result)

    return _first_dict(
        result.get("grounding_validation"),
        result_sub.get("grounding_validation"),
        payload.get("grounding_validation"),
        narration_json.get("grounding_validation"),
        _safe_dict(result.get("structured_narration")).get("grounding_validation"),
        _safe_dict(result_sub.get("structured_narration")).get("grounding_validation"),
    )


def _extract_grounding_violation_codes(validation: Dict[str, Any]) -> list[str]:
    codes: list[str] = []
    for violation in _safe_list(_safe_dict(validation).get("violations")):
        code = _safe_str(_safe_dict(violation).get("code")).strip()
        if code:
            codes.append(code)
    return codes


def _extract_provider_call_diagnostics(result: Dict[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(result)
    result_sub = _safe_dict(result.get("result"))
    payload = _extract_narration_payload(result)
    narration_json = _extract_narration_json(result)

    return _first_dict(
        result.get("provider_call_diagnostics"),
        result_sub.get("provider_call_diagnostics"),
        payload.get("provider_call_diagnostics"),
        narration_json.get("provider_call_diagnostics"),
        _safe_dict(result_sub.get("raw_llm_narration")).get("provider_call_diagnostics"),
        _safe_dict(result_sub.get("runtime_narration")).get("provider_call_diagnostics"),
    )


def _compact_payload(value: Any, limits: Dict[str, Any]) -> Dict[str, Any]:
    value = _safe_dict(value)
    if not value:
        return {}

    compacted: Dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, str):
            compacted[key] = _preview(item, limits["max_text"])
        elif isinstance(item, dict):
            compacted[key] = _cap_dict_keys(item, limits["max_dict_keys"])
        elif isinstance(item, list):
            compacted[key] = _cap_list(item, limits["max_list"])
        else:
            compacted[key] = item

    return _cap_dict_keys(compacted, limits["max_dict_keys"])


def _extract_combat_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract compact combat result fields."""
    result_sub = _safe_dict(result.get("result"))
    combat = _safe_dict(result_sub.get("combat_result"))

    if not combat:
        return {}

    return {
        "hit": combat.get("hit"),
        "damage": combat.get("damage"),
        "defeated": combat.get("defeated"),
        "victory": combat.get("victory"),
        "actor": _safe_str(combat.get("actor")),
        "target": _safe_str(combat.get("target")),
        "reason": _preview(_safe_str(combat.get("reason")), 200),
    }


def _extract_combat_narration_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract combat narration validation summary."""
    result_sub = _safe_dict(result.get("result"))

    return {
        "attempted": result_sub.get("combat_narration_attempted"),
        "accepted": result_sub.get("combat_narration_accepted"),
        "error": _preview(_safe_str(result_sub.get("combat_narration_error")), 300),
        "validation": _preview(_safe_str(result_sub.get("combat_narration_validation")), 500),
        "payload": _preview(_safe_str(result_sub.get("combat_narration_payload")), 1000),
    }


def _extract_narration_debug(result: Dict[str, Any], limits: Dict[str, Any]) -> Dict[str, Any]:
    """Extract LLM/narration debug info."""
    result_sub = _safe_dict(result.get("result"))
    raw_payload = _extract_narration_payload(result)
    narration_json = _extract_narration_json(result)
    grounding_validation = _extract_grounding_validation(result)
    npc = _safe_dict(narration_json.get("npc"))
    provider_call_diagnostics = _extract_provider_call_diagnostics(result)

    # Cap raw LLM text
    raw_text = raw_payload.get("raw_llm_narration") or raw_payload.get("raw_llm_text")
    raw_request = raw_payload.get("raw_llm_request")

    return {
        "llm_called": (
            result.get("llm_called")
            or result_sub.get("llm_called")
            or result_sub.get("used_llm")
            or raw_payload.get("used_llm")
        ),
        "llm_purpose": result_sub.get("llm_purpose") or raw_payload.get("llm_purpose"),
        "narration_status": result_sub.get("narration_status") or raw_payload.get("narration_status"),
        "final_narration": _preview(_extract_narration_preview(result, limits["max_text"]), limits["max_text"]),
        "json_narration": _preview(_safe_str(narration_json.get("narration")), limits["max_text"]),
        "json_action": _preview(_safe_str(narration_json.get("action")), limits["max_text"]),
        "npc_speaker": _safe_str(npc.get("speaker")),
        "npc_line": _preview(_safe_str(npc.get("line")), limits["max_text"]),
        "reward": narration_json.get("reward"),
        "followup_hooks": _cap_list(_safe_list(narration_json.get("followup_hooks")), limits["max_list"]),
        "grounding_validation": grounding_validation,
        "grounding_selected_candidate": _safe_str(grounding_validation.get("selected_candidate")),
        "grounding_fallback_used": bool(grounding_validation.get("fallback_used")),
        "grounding_fallback_source": _safe_str(grounding_validation.get("fallback_source")),
        "grounding_violation_codes": _extract_grounding_violation_codes(grounding_validation),
        "provider_call_diagnostics": _compact_payload(provider_call_diagnostics, limits),
        "provider_valid": provider_call_diagnostics.get("provider_valid"),
        "provider_errors": provider_call_diagnostics.get("provider_errors"),
        "raw_llm_narration_capped": _preview(_safe_str(raw_text), limits["max_text"]),
        "raw_llm_request_capped": _preview(_safe_str(raw_request), limits["max_text"]),
    }


def _extract_extracted_fields(result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract narration, action, npc fields."""
    narration_json = _extract_narration_json(result)
    npc = _safe_dict(narration_json.get("npc"))
    grounding_validation = _extract_grounding_validation(result)

    return {
        "narration": _safe_str(narration_json.get("narration")),
        "action": _safe_str(narration_json.get("action")),
        "npc_speaker": _safe_str(npc.get("speaker")),
        "npc_line": _safe_str(npc.get("line")),
        "reward": narration_json.get("reward"),
        "followup_hooks": _safe_list(narration_json.get("followup_hooks")),
        "grounding_validation": grounding_validation,
    }


def _extract_deterministic_contract(result: Dict[str, Any], limits: Dict[str, Any]) -> Dict[str, Any]:
    """Extract compact turn_contract and resolved_result."""
    result_sub = _safe_dict(result.get("result"))
    narration_payload = _extract_narration_payload(result)

    turn_contract = _first_dict(
        result.get("turn_contract"),
        result_sub.get("turn_contract"),
        narration_payload.get("turn_contract"),
        _safe_dict(narration_payload.get("narration_context")).get("turn_contract"),
        result.get("turn_contract_compact"),
    )
    resolved_result = _first_dict(
        result.get("resolved_result"),
        result_sub.get("resolved_result"),
        result_sub.get("interaction_result"),
        result_sub.get("conversation_result"),
        result.get("resolved_result_compact"),
    )

    return {
        "action_type": _safe_str(turn_contract.get("action_type") or resolved_result.get("action_type")),
        "semantic_action_type": _safe_str(
            turn_contract.get("semantic_action_type") or resolved_result.get("semantic_action_type")
        ),
        "visible_interaction_reason": _safe_str(
            result.get("visible_interaction_reason")
            or result_sub.get("visible_interaction_reason")
            or resolved_result.get("reason")
        ),
        "turn_contract_compact": _cap_dict_keys(turn_contract, limits["max_dict_keys"]),
        "resolved_result_compact": _cap_dict_keys(resolved_result, limits["max_dict_keys"]),
    }


def _extract_compact_state_deltas(result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract compact state changes (currency, inventory, etc.)."""
    # This is a placeholder - actual implementation would extract deltas
    return {
        "note": "State delta extraction not yet implemented",
    }


# ---------------------------------------------------------------------------
# Turn sanitization based on detail level
# ---------------------------------------------------------------------------

def sanitize_turn_for_summary(
    turn: Dict[str, Any],
    detail: str = "summary",
) -> Dict[str, Any]:
    """
    Sanitize a single turn for global summary output.

    Keeps only essential diagnostic fields and strips large state blobs.
    """
    if not isinstance(turn, dict):
        return turn

    limits = _get_limits(detail)
    preserve_keys = PRESERVE_TURN_KEYS_SUMMARY.copy()

    if detail in ("debug", "full"):
        preserve_keys = PRESERVE_TURN_KEYS_DEBUG.copy()
    if detail == "full":
        preserve_keys = PRESERVE_TURN_KEYS_FULL.copy()

    sanitized = {}
    result = _safe_dict(turn.get("result"))

    # Always-preserved fields
    for key in preserve_keys:
        if key in turn:
            sanitized[key] = turn[key]

    if result:
        sanitized.setdefault("raw_result_keys", sorted([str(k) for k in result.keys()]))
        sanitized.setdefault("narration_preview", _extract_narration_preview(result, limits["max_text"]))

    if detail in ("debug", "full") and result:
        narration_payload = _extract_narration_payload(result)
        narration_json = _extract_narration_json(result)
        grounding_validation = _extract_grounding_validation(result)

        sanitized["extracted"] = _extract_extracted_fields(result)
        sanitized["narration_debug"] = _extract_narration_debug(result, limits)
        sanitized["narration_payload_compact"] = _compact_payload(narration_payload, limits)
        sanitized["structured_narration_compact"] = _compact_payload(narration_json, limits)
        sanitized["grounding_validation"] = grounding_validation
        sanitized["grounding_fallback"] = bool(
            grounding_validation.get("fallback_used")
            or narration_json.get("grounding_fallback")
            or narration_payload.get("grounding_fallback")
        )
        sanitized["grounding_selected_candidate"] = _safe_str(
            grounding_validation.get("selected_candidate")
        )
        sanitized["grounding_fallback_source"] = _safe_str(
            grounding_validation.get("fallback_source")
        )
        sanitized["grounding_violation_codes"] = _extract_grounding_violation_codes(
            grounding_validation
        )
        sanitized["grounding_primary_violations"] = _safe_list(
            grounding_validation.get("primary_violations")
        )
        sanitized.update(_extract_deterministic_contract(result, limits))
        stateful_contract = _safe_dict(
            result.get("stateful_runtime_narration_contract")
            or _safe_dict(result.get("result")).get("stateful_runtime_narration_contract")
        )
        if stateful_contract:
            sanitized["stateful_runtime_narration_contract"] = stateful_contract
        sanitized["compact_state_deltas"] = _extract_compact_state_deltas(result)
    elif result:
        grounding_validation = _extract_grounding_validation(result)
        if grounding_validation:
            sanitized["grounding_validation"] = grounding_validation
            sanitized["grounding_fallback"] = bool(grounding_validation.get("fallback_used"))
            sanitized["grounding_selected_candidate"] = _safe_str(
                grounding_validation.get("selected_candidate")
            )
            sanitized["grounding_fallback_source"] = _safe_str(
                grounding_validation.get("fallback_source")
            )

    spatial_check_results = turn.get("spatial_check_results")
    if isinstance(spatial_check_results, list):
        if detail in ("debug", "full"):
            sanitized["spatial_check_results"] = [
                {
                    "check_type": item.get("check_type"),
                    "ok": item.get("ok"),
                    "expected_ok": item.get("expected_ok"),
                    "actual_ok": item.get("actual_ok"),
                    "expected_reason": item.get("expected_reason"),
                    "actual_reason": item.get("actual_reason"),
                    "expected_area_id": item.get("expected_area_id"),
                    "actual_area_id": item.get("actual_area_id"),
                    "expected_entity_ids": item.get("expected_entity_ids"),
                    "actual_entity_ids": item.get("actual_entity_ids"),
                    "error": item.get("error"),
                }
                for item in spatial_check_results[:50]
                if isinstance(item, dict)
            ]
        else:
            sanitized["spatial_check_results"] = [
                {
                    "check_type": item.get("check_type"),
                    "ok": item.get("ok"),
                    "actual_reason": item.get("actual_reason"),
                    "error": item.get("error"),
                }
                for item in turn.get("spatial_check_results", [])[:20]
                if isinstance(item, dict)
            ]

    memory_check_results = turn.get("memory_check_results")
    if isinstance(memory_check_results, list):
        sanitized["memory_check_results"] = [
            {
                "check_type": item.get("check_type"),
                "ok": item.get("ok"),
                "subject_id": item.get("subject_id"),
                "expected_event_ids": item.get("expected_event_ids"),
                "forbidden_event_ids": item.get("forbidden_event_ids"),
                "actual_event_ids": item.get("actual_event_ids"),
                "error": item.get("error"),
            }
            for item in memory_check_results[:50]
            if isinstance(item, dict)
        ]

    social_check_results = turn.get("social_check_results")
    if isinstance(social_check_results, list):
        sanitized["social_check_results"] = [
            {
                "check_type": item.get("check_type"),
                "ok": item.get("ok"),
                "npc_id": item.get("npc_id"),
                "actor_id": item.get("actor_id"),
                "result_key": item.get("result_key"),
                "expected_ok": item.get("expected_ok"),
                "expected_stance": item.get("expected_stance"),
                "expected_escalation": item.get("expected_escalation"),
                "actual_stance": item.get("actual_stance"),
                "relationship": item.get("relationship"),
                "actual": item.get("actual"),
                "validation": item.get("validation"),
                "failures": item.get("failures"),
                "available_result_keys": item.get("available_result_keys"),
                "error": item.get("error"),
            }
            for item in social_check_results[:50]
            if isinstance(item, dict)
        ]

    quest_puzzle_check_results = turn.get("quest_puzzle_check_results")
    if isinstance(quest_puzzle_check_results, list):
        sanitized["quest_puzzle_check_results"] = [
            {
                "check_type": item.get("check_type"),
                "ok": item.get("ok"),
                "quest_id": item.get("quest_id"),
                "puzzle_id": item.get("puzzle_id"),
                "expected_stage": item.get("expected_stage"),
                "actual_stage": item.get("actual_stage"),
                "expected_state": item.get("expected_state"),
                "actual_state": item.get("actual_state"),
                "expected_status": item.get("expected_status"),
                "actual_status": item.get("actual_status"),
                "objective_id": item.get("objective_id"),
                "expected_count": item.get("expected_count"),
                "actual_count": item.get("actual_count"),
                "expected": item.get("expected"),
                "actual": item.get("actual"),
                "condition_result": item.get("condition_result"),
                "rewards": item.get("rewards"),
                "error": item.get("error"),
            }
            for item in quest_puzzle_check_results[:50]
            if isinstance(item, dict)
        ]

    story_m1_m3_check_results = turn.get("story_m1_m3_check_results")
    if isinstance(story_m1_m3_check_results, list):
        sanitized["story_m1_m3_check_results"] = [
            {
                "check_type": item.get("check_type"),
                "ok": item.get("ok"),
                "lore_id": item.get("lore_id"),
                "arc_id": item.get("arc_id"),
                "entry": item.get("entry"),
                "arc": item.get("arc"),
                "expected_ok": item.get("expected_ok"),
                "actual_ok": item.get("actual_ok"),
                "condition_result": item.get("condition_result"),
                "failures": item.get("failures"),
                "link_count": item.get("link_count"),
                "max_link_count": item.get("max_link_count"),
                "error": item.get("error"),
            }
            for item in story_m1_m3_check_results[:50]
            if isinstance(item, dict)
        ]

    story_event_m4_m6_check_results = turn.get("story_event_m4_m6_check_results")
    if isinstance(story_event_m4_m6_check_results, list):
        sanitized["story_event_m4_m6_check_results"] = [
            {
                "check_type": item.get("check_type"),
                "ok": item.get("ok"),
                "event_id": item.get("event_id"),
                "arc_id": item.get("arc_id"),
                "lore_id": item.get("lore_id"),
                "quest_id": item.get("quest_id"),
                "npc_id": item.get("npc_id"),
                "subject_id": item.get("subject_id"),
                "source_story_event_id": item.get("source_story_event_id"),
                "expected_event_id": item.get("expected_event_id"),
                "actual_event_ids": item.get("actual_event_ids"),
                "applied": item.get("applied"),
                "validation": item.get("validation"),
                "arc": item.get("arc"),
                "entry": item.get("entry"),
                "quest": item.get("quest"),
                "relationship": item.get("relationship"),
                "rows": item.get("rows"),
                "retrieved": item.get("retrieved"),
                "failures": item.get("failures"),
                "error": item.get("error"),
            }
            for item in story_event_m4_m6_check_results[:50]
            if isinstance(item, dict)
        ]

    escalation_m7_m9_check_results = turn.get("escalation_m7_m9_check_results")
    if isinstance(escalation_m7_m9_check_results, list):
        sanitized["escalation_m7_m9_check_results"] = [
            {
                "check_type": item.get("check_type"),
                "ok": item.get("ok"),
                "rule_id": item.get("rule_id"),
                "arc_id": item.get("arc_id"),
                "event_id": item.get("event_id"),
                "expected_eligible": item.get("expected_eligible"),
                "actual_eligible": item.get("actual_eligible"),
                "expected_eligible_count": item.get("expected_eligible_count"),
                "expected_first_rule_id": item.get("expected_first_rule_id"),
                "expected_count": item.get("expected_count"),
                "actual_count": item.get("actual_count"),
                "expected_first_event_id": item.get("expected_first_event_id"),
                "evaluation": item.get("evaluation"),
                "pressure": item.get("pressure"),
                "application": item.get("application"),
                "arc": item.get("arc"),
                "applied": item.get("applied"),
                "failures": item.get("failures"),
                "error": item.get("error"),
            }
            for item in escalation_m7_m9_check_results[:50]
            if isinstance(item, dict)
        ]

    story_proposal_m10_m12_check_results = turn.get("story_proposal_m10_m12_check_results")
    if isinstance(story_proposal_m10_m12_check_results, list):
        sanitized["story_proposal_m10_m12_check_results"] = [
            {
                "check_type": item.get("check_type"),
                "ok": item.get("ok"),
                "expected_ok": item.get("expected_ok"),
                "actual_ok": item.get("actual_ok"),
                "required_error": item.get("required_error"),
                "validation": item.get("validation"),
                "counts": item.get("counts"),
                "failures": item.get("failures"),
                "error": item.get("error"),
            }
            for item in story_proposal_m10_m12_check_results[:50]
            if isinstance(item, dict)
        ]

    story_pack_m13_m15_check_results = turn.get("story_pack_m13_m15_check_results")
    if isinstance(story_pack_m13_m15_check_results, list):
        sanitized["story_pack_m13_m15_check_results"] = [
            {
                "check_type": item.get("check_type"),
                "ok": item.get("ok"),
                "expected_ok": item.get("expected_ok"),
                "actual_ok": item.get("actual_ok"),
                "required_reason": item.get("required_reason"),
                "pack_id": item.get("pack_id"),
                "lore_id": item.get("lore_id"),
                "arc_id": item.get("arc_id"),
                "event_id": item.get("event_id"),
                "rule_id": item.get("rule_id"),
                "quest_id": item.get("quest_id"),
                "import_result": item.get("import_result"),
                "imported": item.get("imported"),
                "entry": item.get("entry"),
                "arc": item.get("arc"),
                "event": item.get("event"),
                "rule": item.get("rule"),
                "quest": item.get("quest"),
                "failures": item.get("failures"),
                "imported_pack_count": item.get("imported_pack_count"),
                "event_definition_count": item.get("event_definition_count"),
                "rule_definition_count": item.get("rule_definition_count"),
                "error": item.get("error"),
            }
            for item in story_pack_m13_m15_check_results[:50]
            if isinstance(item, dict)
        ]

    dialogue_m16_m18_check_results = turn.get("dialogue_m16_m18_check_results")
    if isinstance(dialogue_m16_m18_check_results, list):
        sanitized["dialogue_m16_m18_check_results"] = [
            {
                "check_type": item.get("check_type"),
                "ok": item.get("ok"),
                "npc_id": item.get("npc_id"),
                "context": item.get("context"),
                "propagation": item.get("propagation"),
                "subject_id": item.get("subject_id"),
                "expected_lore_id": item.get("expected_lore_id"),
                "matched": item.get("matched"),
                "retrieved": item.get("retrieved"),
                "lore_id": item.get("lore_id"),
                "expected_truth_status": item.get("expected_truth_status"),
                "actual_truth_status": item.get("actual_truth_status"),
                "entry": item.get("entry"),
                "error": item.get("error"),
            }
            for item in dialogue_m16_m18_check_results[:50]
            if isinstance(item, dict)
        ]

    npc_evolution_m19_m21_check_results = turn.get("npc_evolution_m19_m21_check_results")
    if isinstance(npc_evolution_m19_m21_check_results, list):
        sanitized["npc_evolution_m19_m21_check_results"] = [
            {
                "check_type": item.get("check_type"),
                "ok": item.get("ok"),
                "npc_id": item.get("npc_id"),
                "evolution": item.get("evolution"),
                "failures": item.get("failures"),
                "expected_ok": item.get("expected_ok"),
                "actual_ok": item.get("actual_ok"),
                "condition_result": item.get("condition_result"),
                "transition_result": item.get("transition_result"),
                "history_count": item.get("history_count"),
                "max_history": item.get("max_history"),
                "error": item.get("error"),
            }
            for item in npc_evolution_m19_m21_check_results[:50]
            if isinstance(item, dict)
        ]

    campaign_director_m22_m24_check_results = turn.get("campaign_director_m22_m24_check_results")
    if isinstance(campaign_director_m22_m24_check_results, list):
        sanitized["campaign_director_m22_m24_check_results"] = [
            {
                "check_type": item.get("check_type"),
                "ok": item.get("ok"),
                "evaluation": item.get("evaluation"),
                "applied": item.get("applied"),
                "snapshot": item.get("snapshot"),
                "arc_id": item.get("arc_id"),
                "arc": item.get("arc"),
                "event_id": item.get("event_id"),
                "npc_id": item.get("npc_id"),
                "evolution": item.get("evolution"),
                "expected_eligible_count": item.get("expected_eligible_count"),
                "expected_first_event_id": item.get("expected_first_event_id"),
                "expected_applied_count": item.get("expected_applied_count"),
                "expected_reason": item.get("expected_reason"),
                "failures": item.get("failures"),
                "error": item.get("error"),
            }
            for item in campaign_director_m22_m24_check_results[:50]
            if isinstance(item, dict)
        ]

    story_event_queue_m25_m27_check_results = turn.get("story_event_queue_m25_m27_check_results")
    if isinstance(story_event_queue_m25_m27_check_results, list):
        sanitized["story_event_queue_m25_m27_check_results"] = [
            {
                "check_type": item.get("check_type"),
                "ok": item.get("ok"),
                "enqueue_result": item.get("enqueue_result"),
                "process_result": item.get("process_result"),
                "pending": item.get("pending"),
                "history": item.get("history"),
                "rows": item.get("rows"),
                "arc_id": item.get("arc_id"),
                "arc": item.get("arc"),
                "event_id": item.get("event_id"),
                "applied": item.get("applied"),
                "expected_count": item.get("expected_count"),
                "expected_event_id": item.get("expected_event_id"),
                "expected_status": item.get("expected_status"),
                "expected_applied": item.get("expected_applied"),
                "failures": item.get("failures"),
                "error": item.get("error"),
            }
            for item in story_event_queue_m25_m27_check_results[:50]
            if isinstance(item, dict)
        ]

    companion_m28_m30_check_results = turn.get("companion_m28_m30_check_results")
    if isinstance(companion_m28_m30_check_results, list):
        sanitized["companion_m28_m30_check_results"] = [
            {
                "check_type": item.get("check_type"),
                "ok": item.get("ok"),
                "npc_id": item.get("npc_id"),
                "evaluation": item.get("evaluation"),
                "context": item.get("context"),
                "accept_result": item.get("accept_result"),
                "refuse_result": item.get("refuse_result"),
                "member": item.get("member"),
                "expected_eligible": item.get("expected_eligible"),
                "expected_reason": item.get("expected_reason"),
                "expected_ok": item.get("expected_ok"),
                "expected_present": item.get("expected_present"),
                "failures": item.get("failures"),
                "error": item.get("error"),
            }
            for item in companion_m28_m30_check_results[:50]
            if isinstance(item, dict)
        ]

    campaign_journal_m31_m33_check_results = turn.get("campaign_journal_m31_m33_check_results")
    if isinstance(campaign_journal_m31_m33_check_results, list):
        sanitized["campaign_journal_m31_m33_check_results"] = [
            {
                "check_type": item.get("check_type"),
                "ok": item.get("ok"),
                "record_result": item.get("record_result"),
                "journal": item.get("journal"),
                "recap": item.get("recap"),
                "matched": item.get("matched"),
                "known_lore": item.get("known_lore"),
                "expected_summary_contains": item.get("expected_summary_contains"),
                "expected_kind": item.get("expected_kind"),
                "expected_arc_id": item.get("expected_arc_id"),
                "expected_pending_event_id": item.get("expected_pending_event_id"),
                "expected_npc_id": item.get("expected_npc_id"),
                "expected_party_npc_id": item.get("expected_party_npc_id"),
                "expected_truth_status": item.get("expected_truth_status"),
                "expected_present": item.get("expected_present"),
                "max_items": item.get("max_items"),
                "error": item.get("error"),
            }
            for item in campaign_journal_m31_m33_check_results[:50]
            if isinstance(item, dict)
        ]

    story_authoring_m34_m36_check_results = turn.get("story_authoring_m34_m36_check_results")
    if isinstance(story_authoring_m34_m36_check_results, list):
        sanitized["story_authoring_m34_m36_check_results"] = [
            {
                "check_type": item.get("check_type"),
                "ok": item.get("ok"),
                "authoring_result": item.get("authoring_result"),
                "attempts": item.get("attempts"),
                "matched": item.get("matched"),
                "pack_id": item.get("pack_id"),
                "imported": item.get("imported"),
                "attempt_count": item.get("attempt_count"),
                "max_attempts": item.get("max_attempts"),
                "expected_ok": item.get("expected_ok"),
                "expected_reason": item.get("expected_reason"),
                "expected_status": item.get("expected_status"),
                "expected_validation_ok": item.get("expected_validation_ok"),
                "expected_import_ok": item.get("expected_import_ok"),
                "must_contain": item.get("must_contain"),
                "must_not_contain": item.get("must_not_contain"),
                "error": item.get("error"),
            }
            for item in story_authoring_m34_m36_check_results[:50]
            if isinstance(item, dict)
        ]

    story_authoring_approval_m37_m39_check_results = turn.get("story_authoring_approval_m37_m39_check_results")
    if isinstance(story_authoring_approval_m37_m39_check_results, list):
        sanitized["story_authoring_approval_m37_m39_check_results"] = [
            {
                "check_type": item.get("check_type"),
                "ok": item.get("ok"),
                "draft_result": item.get("draft_result"),
                "listing": item.get("listing"),
                "approve_result": item.get("approve_result"),
                "reject_result": item.get("reject_result"),
                "pending_id": item.get("pending_id"),
                "pack_id": item.get("pack_id"),
                "imported": item.get("imported"),
                "history": item.get("history"),
                "matched": item.get("matched"),
                "pending_count": item.get("pending_count"),
                "history_count": item.get("history_count"),
                "expected_ok": item.get("expected_ok"),
                "expected_reason": item.get("expected_reason"),
                "expected_count": item.get("expected_count"),
                "expected_proposal_id": item.get("expected_proposal_id"),
                "expected_status": item.get("expected_status"),
                "expected_present": item.get("expected_present"),
                "error": item.get("error"),
            }
            for item in story_authoring_approval_m37_m39_check_results[:50]
            if isinstance(item, dict)
        ]

    story_authoring_inspector_m40_m42_check_results = turn.get("story_authoring_inspector_m40_m42_check_results")
    if isinstance(story_authoring_inspector_m40_m42_check_results, list):
        sanitized["story_authoring_inspector_m40_m42_check_results"] = [
            {
                "check_type": item.get("check_type"),
                "ok": item.get("ok"),
                "payload": item.get("payload"),
                "draft_result": item.get("draft_result"),
                "approve_result": item.get("approve_result"),
                "reject_result": item.get("reject_result"),
                "pending_id": item.get("pending_id"),
                "pack_id": item.get("pack_id"),
                "imported": item.get("imported"),
                "expected_pending_count": item.get("expected_pending_count"),
                "expected_proposal_id": item.get("expected_proposal_id"),
                "expected_ok": item.get("expected_ok"),
                "expected_reason": item.get("expected_reason"),
                "expected_present": item.get("expected_present"),
                "limit": item.get("limit"),
                "error": item.get("error"),
            }
            for item in story_authoring_inspector_m40_m42_check_results[:50]
            if isinstance(item, dict)
        ]

    story_pack_activation_m43_m45_check_results = turn.get("story_pack_activation_m43_m45_check_results")
    if isinstance(story_pack_activation_m43_m45_check_results, list):
        sanitized["story_pack_activation_m43_m45_check_results"] = [
            {
                "check_type": item.get("check_type"),
                "ok": item.get("ok"),
                "import_result": item.get("import_result"),
                "activate_result": item.get("activate_result"),
                "deactivate_result": item.get("deactivate_result"),
                "snapshot": item.get("snapshot"),
                "evaluation": item.get("evaluation"),
                "applied": item.get("applied"),
                "draft": item.get("draft"),
                "approve": item.get("approve"),
                "pack_id": item.get("pack_id"),
                "actual_active": item.get("actual_active"),
                "expected_active": item.get("expected_active"),
                "expected_eligible_count": item.get("expected_eligible_count"),
                "expected_registered_rule_count": item.get("expected_registered_rule_count"),
                "expected_applied_count": item.get("expected_applied_count"),
                "expected_reason": item.get("expected_reason"),
                "error": item.get("error"),
            }
            for item in story_pack_activation_m43_m45_check_results[:50]
            if isinstance(item, dict)
        ]

    story_arc_milestones_m46_m48_check_results = turn.get("story_arc_milestones_m46_m48_check_results")
    if isinstance(story_arc_milestones_m46_m48_check_results, list):
        sanitized["story_arc_milestones_m46_m48_check_results"] = [
            {
                "check_type": item.get("check_type"),
                "ok": item.get("ok"),
                "payload": item.get("payload"),
                "actions": item.get("actions"),
                "expected_mode": item.get("expected_mode"),
                "expected_objective_id": item.get("expected_objective_id"),
                "expected_action_category": item.get("expected_action_category"),
                "expected_category": item.get("expected_category"),
                "expected_objective_ids": item.get("expected_objective_ids"),
                "expected_ok": item.get("expected_ok"),
                "expected_reason": item.get("expected_reason"),
                "expected_summary_contains": item.get("expected_summary_contains"),
                "expected_max": item.get("expected_max"),
                "error": item.get("error"),
            }
            for item in story_arc_milestones_m46_m48_check_results[:50]
            if isinstance(item, dict)
        ]

    player_action_context_m52_m54_check_results = turn.get("player_action_context_m52_m54_check_results")
    if isinstance(player_action_context_m52_m54_check_results, list):
        sanitized["player_action_context_m52_m54_check_results"] = [
            {
                "check_type": item.get("check_type"),
                "ok": item.get("ok"),
                "payload": item.get("payload"),
                "actions": item.get("actions"),
                "expected_mode": item.get("expected_mode"),
                "expected_objective_id": item.get("expected_objective_id"),
                "expected_action_category": item.get("expected_action_category"),
                "expected_category": item.get("expected_category"),
                "expected_first_objective_id": item.get("expected_first_objective_id"),
                "must_not_contain": item.get("must_not_contain"),
                "limit": item.get("limit"),
                "error": item.get("error"),
            }
            for item in player_action_context_m52_m54_check_results[:50]
            if isinstance(item, dict)
        ]

    return sanitized


# ---------------------------------------------------------------------------
# Scenario summary sanitization
# ---------------------------------------------------------------------------

def sanitize_scenario_summary(
    summary: Dict[str, Any],
    detail: str = "summary",
) -> Dict[str, Any]:
    """
    Sanitize a full scenario summary row for global summary output.

    Strips large fields from turns and adds scenario-level previews.
    """
    if not isinstance(summary, dict):
        return summary

    limits = _get_limits(detail)

    sanitized = {
        "scenario": _safe_str(summary.get("scenario")),
        "session_id": _safe_str(summary.get("session_id")),
        "seeded_currency": summary.get("seeded_currency"),
        "error": summary.get("error"),
        "setup_error_type": summary.get("setup_error_type"),
        "setup_error": summary.get("setup_error"),
        "setup_error_repr": summary.get("setup_error_repr"),
        "regression_warnings": summary.get("regression_warnings") or [],
        "scenario_warnings": summary.get("scenario_warnings") or [],
    }

    # Sanitize each turn
    turns = _safe_list(summary.get("turns"))
    sanitized["turns"] = [sanitize_turn_for_summary(t, detail) for t in turns]

    # Aggregate warnings
    for warning_key in ("regression_warnings", "scenario_warnings"):
        warnings = []
        for turn in turns:
            warnings.extend(_safe_list(turn.get(warning_key)))
        if warnings:
            sanitized[warning_key] = warnings[:limits["max_list"]]

    # Preserve error if present
    if summary.get("error"):
        sanitized["error"] = _preview(_safe_str(summary["error"]), limits["max_text"])

    # Add turn count and summary stats
    sanitized["_stats"] = {
        "turn_count": len(turns),
        "has_error": bool(summary.get("error")),
        "warning_count": len(sanitized.get("regression_warnings", []))
        + len(sanitized.get("scenario_warnings", [])),
    }

    return sanitized


# ---------------------------------------------------------------------------
# Write per-scenario debug artifact
# ---------------------------------------------------------------------------

def write_scenario_debug_artifact(
    scenario_name: str,
    scenario_summary: Dict[str, Any],
    output_dir: str,
    detail: str = "debug",
) -> str:
    """
    Write per-scenario debug JSON artifact with bounded detail.

    Returns the path to the written file.
    """
    from pathlib import Path

    output_path = Path(output_dir)
    scenarios_dir = output_path / "scenarios"
    scenarios_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize with debug/full detail
    sanitized = sanitize_scenario_summary(scenario_summary, detail)

    filename = f"{scenario_name}.{detail}.json"
    filepath = scenarios_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(sanitized, f, indent=2, ensure_ascii=False, default=str)

    return str(filepath)
