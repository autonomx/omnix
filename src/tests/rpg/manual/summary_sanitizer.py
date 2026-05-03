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
        if key in STRIP_KEYS_FROM_RESULT:
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
        elif detail in ("debug", "full") and key == "turn_contract":
            # Keep compact version for debug/full
            compacted[f"{key}_compact"] = _cap_dict_keys(_safe_dict(value), limits["max_dict_keys"])
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
    raw_payload = _safe_dict(result_sub.get("raw_llm_narration"))

    narration_json = _safe_dict(raw_payload.get("narration_json"))
    npc = _safe_dict(narration_json.get("npc"))

    # Cap raw LLM text
    raw_text = raw_payload.get("raw_llm_narration") or raw_payload.get("raw_llm_text")
    raw_request = raw_payload.get("raw_llm_request")

    return {
        "llm_called": result_sub.get("llm_called") or result_sub.get("used_llm"),
        "llm_purpose": result_sub.get("llm_purpose"),
        "narration_status": result_sub.get("narration_status"),
        "final_narration": _preview(_extract_narration_preview(result, limits["max_text"]), limits["max_text"]),
        "json_narration": _preview(_safe_str(narration_json.get("narration")), limits["max_text"]),
        "json_action": _preview(_safe_str(narration_json.get("action")), limits["max_text"]),
        "npc_speaker": _safe_str(npc.get("speaker")),
        "npc_line": _preview(_safe_str(npc.get("line")), limits["max_text"]),
        "raw_llm_narration_capped": _preview(_safe_str(raw_text), limits["max_text"]),
        "raw_llm_request_capped": _preview(_safe_str(raw_request), limits["max_text"]),
    }


def _extract_extracted_fields(result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract narration, action, npc fields."""
    result_sub = _safe_dict(result.get("result"))
    raw_payload = _safe_dict(result_sub.get("raw_llm_narration"))
    narration_json = _safe_dict(raw_payload.get("narration_json"))
    npc = _safe_dict(narration_json.get("npc"))

    return {
        "narration": _safe_str(narration_json.get("narration")),
        "action": _safe_str(narration_json.get("action")),
        "npc_speaker": _safe_str(npc.get("speaker")),
        "npc_line": _safe_str(npc.get("line")),
        "reward": _safe_str(narration_json.get("reward")),
        "followup_hooks": _safe_list(narration_json.get("followup_hooks")),
    }


def _extract_deterministic_contract(result: Dict[str, Any], limits: Dict[str, Any]) -> Dict[str, Any]:
    """Extract compact turn_contract and resolved_result."""
    result_sub = _safe_dict(result.get("result"))

    turn_contract = _safe_dict(result.get("turn_contract"))
    resolved_result = _safe_dict(result_sub.get("resolved_result"))

    return {
        "action_type": _safe_str(turn_contract.get("action_type")),
        "semantic_action_type": _safe_str(turn_contract.get("semantic_action_type")),
        "visible_interaction_reason": _safe_str(result.get("visible_interaction_reason")),
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

    # Ensure narration preview
    if "narration_preview" not in sanitized:
        sanitized["narration_preview"] = _extract_narration_preview(result, limits["max_text"])

    # Combat summary
    combat_summary = _extract_combat_summary(result)
    if combat_summary:
        sanitized["combat_result"] = combat_summary

    # Combat narration summary
    combat_narration = _extract_combat_narration_summary(result)
    for k, v in combat_narration.items():
        if v is not None and v != "":
            sanitized[f"combat_narration_{k}"] = v

    # LLM status
    if "llm_called" not in sanitized:
        sanitized["llm_called"] = result.get("used_llm") or result.get("llm_called")

    # Visible interaction reason
    if "visible_interaction_reason" not in sanitized:
        interaction_result = _safe_dict(_safe_dict(result.get("result"))).get("interaction_result")
        if interaction_result:
            reason = _safe_str(interaction_result.get("reason"))
            if reason and reason not in ("", "unknown"):
                sanitized["visible_interaction_reason"] = reason

    # Raw result keys (for debugging)
    if result:
        sanitized["raw_result_keys"] = sorted(result.keys())[:limits["max_dict_keys"]]

    # Detail-specific fields
    if limits["include_debug_fields"]:
        # Narration debug info
        sanitized["narration_debug"] = _extract_narration_debug(result, limits)

        # Deterministic contract
        sanitized.update(_extract_deterministic_contract(result, limits))

        # Combat narration payload
        combat_payload = result.get("combat_narration_payload")
        if combat_payload:
            sanitized["combat_narration_payload"] = _preview(_safe_str(combat_payload), limits["max_text"])

    if limits["include_extracted"]:
        sanitized["extracted"] = _extract_extracted_fields(result)

    if limits["include_full_state"]:
        sanitized["full_state"] = _cap_dict_keys(result, limits["max_dict_keys"])

    # Compact result (stripped version)
    if result and detail != "full":
        sanitized["result_compact"] = compact_result_for_summary(result, detail)

    # Preserve error if present
    if turn.get("error"):
        sanitized["error"] = _preview(_safe_str(turn["error"]), limits["max_text"])

    # Preserve warnings
    for warning_key in ("regression_warnings", "scenario_warnings"):
        if warning_key in turn:
            sanitized[warning_key] = _safe_list(turn[warning_key])[:limits["max_list"]]

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