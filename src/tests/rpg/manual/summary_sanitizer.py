"""
Summary sanitizer for manual RPG test artifacts.

Reduces artifact bloat by stripping or capping large fields while preserving
essential diagnostic information.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, Optional

from tests.rpg.manual.safe import _safe_dict, _safe_list, _safe_str


# ---------------------------------------------------------------------------
# Constants
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

# Keys to always preserve in sanitized turn output
PRESERVE_TURN_KEYS = {
    "turn_index",
    "player_input",
    "ok",
    "error",
    "llm_called",
    "llm_purpose",
    "combat_narration_attempted",
    "combat_narration_accepted",
    "combat_narration_error",
    "combat_narration_validation",
    "combat_result",
    "visible_interaction_reason",
    "regression_warnings",
    "scenario_warnings",
    "raw_result_keys",
    "narration_preview",
}

# Max length for text previews
MAX_PREVIEW_LENGTH = 500
MAX_JSON_PREVIEW_LENGTH = 2000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _preview(text: Optional[str], max_len: int = MAX_PREVIEW_LENGTH) -> str:
    """Return a truncated preview of text."""
    if text is None:
        return ""
    s = _safe_str(text)
    if len(s) <= max_len:
        return s
    return s[:max_len] + f"... [truncated, {len(s)} chars total]"


def _compact_json_preview(value: Any, max_len: int = MAX_JSON_PREVIEW_LENGTH) -> str:
    """Return a compact JSON preview of a value."""
    import json
    try:
        text = json.dumps(value, indent=2, ensure_ascii=False, default=str)
    except Exception:
        text = str(value)
    return _preview(text, max_len)


def _cap_list(value: Any, max_items: int = 10) -> Any:
    """Cap list length for summary output."""
    if isinstance(value, list):
        if len(value) <= max_items:
            return value
        return value[:max_items] + [f"... {len(value) - max_items} more items"]
    return value


def _strip_large_state(state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Strip large fields from a state dict (session, runtime_state, etc.)."""
    if not isinstance(state, dict):
        return {}
    stripped = copy.deepcopy(state)

    # Remove or cap large fields
    for key in list(stripped.keys()):
        value = stripped[key]
        if key in CAP_KEYS_IN_SESSION:
            if isinstance(value, (list, dict)):
                stripped[key] = f"[stripped: {type(value).__name__} with {len(value)} items]"
        elif key in {"inventory", "world_state", "journal", "quests", "npcs"}:
            stripped[key] = _cap_list(value, max_items=5)
        elif isinstance(value, dict) and len(value) > 20:
            stripped[key] = f"[stripped: dict with {len(value)} keys]"
        elif isinstance(value, list) and len(value) > 50:
            stripped[key] = f"[stripped: list with {len(value)} items]"

    return stripped


# ---------------------------------------------------------------------------
# Result compaction
# ---------------------------------------------------------------------------

def compact_result_for_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compact a turn result for summary output.

    Removes large state blobs while preserving essential diagnostic fields.
    """
    if not isinstance(result, dict):
        return result

    # Shallow copy to avoid modifying original in caller
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
            compacted[key] = compact_result_for_summary(value)
        elif key in {"authoritative", "raw_llm_narrative"}:
            # Keep these but strip their large sub-fields
            compacted[key] = _strip_large_state(_safe_dict(value))
        else:
            compacted[key] = value

    return compacted


# ---------------------------------------------------------------------------
# Turn sanitization
# ---------------------------------------------------------------------------

def _extract_narration_preview(result: Dict[str, Any]) -> str:
    """Extract a short narration preview from a turn result."""
    # Check direct narration fields
    for key in ("narration", "narrative", "text", "rendered_narration"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return _preview(value.strip())

    # Check nested result
    result_sub = _safe_dict(result.get("result"))
    for key in ("narration", "narrative", "text", "rendered_narration"):
        value = result_sub.get(key)
        if isinstance(value, str) and value.strip():
            return _preview(value.strip())

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
    }


def sanitize_turn_for_summary(turn: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize a single turn summary for global summary output.

    Keeps only essential diagnostic fields and strips large state blobs.
    """
    if not isinstance(turn, dict):
        return turn

    sanitized = {}
    result = _safe_dict(turn.get("result"))

    # Always-preserved fields
    for key in PRESERVE_TURN_KEYS:
        if key in turn:
            sanitized[key] = turn[key]

    # Ensure narration preview
    if "narration_preview" not in sanitized:
        sanitized["narration_preview"] = _extract_narration_preview(result)

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
        interaction_result = _safe_dict(_safe_dict(result.get("result")).get("interaction_result"))
        if interaction_result:
            reason = _safe_str(interaction_result.get("reason"))
            if reason and reason not in ("", "unknown"):
                sanitized["visible_interaction_reason"] = reason

    # Raw result keys (for debugging)
    if result:
        sanitized["raw_result_keys"] = sorted(result.keys())

    # Compact result (stripped version)
    if result:
        sanitized["result_compact"] = compact_result_for_summary(result)

    # Preserve error if present
    if turn.get("error"):
        sanitized["error"] = _preview(_safe_str(turn["error"]), 500)

    # Preserve warnings
    for warning_key in ("regression_warnings", "scenario_warnings"):
        if warning_key in turn:
            sanitized[warning_key] = _safe_list(turn[warning_key])

    return sanitized


# ---------------------------------------------------------------------------
# Scenario summary sanitization
# ---------------------------------------------------------------------------

def sanitize_scenario_summary(summary: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize a full scenario summary row for global summary output.

    Strips large fields from turns and adds scenario-level previews.
    """
    if not isinstance(summary, dict):
        return summary

    sanitized = {
        "scenario": _safe_str(summary.get("scenario")),
        "session_id": _safe_str(summary.get("session_id")),
        "seeded_currency": summary.get("seeded_currency"),
    }

    # Sanitize each turn
    turns = _safe_list(summary.get("turns"))
    sanitized["turns"] = [sanitize_turn_for_summary(t) for t in turns]

    # Aggregate warnings
    for warning_key in ("regression_warnings", "scenario_warnings"):
        warnings = []
        for turn in turns:
            warnings.extend(_safe_list(turn.get(warning_key)))
        if warnings:
            sanitized[warning_key] = warnings

    # Preserve error if present
    if summary.get("error"):
        sanitized["error"] = _preview(_safe_str(summary["error"]), 500)

    # Add turn count and summary stats
    sanitized["_stats"] = {
        "turn_count": len(turns),
        "has_error": bool(summary.get("error")),
        "warning_count": len(sanitized.get("regression_warnings", []))
        + len(sanitized.get("scenario_warnings", [])),
    }

    return sanitized