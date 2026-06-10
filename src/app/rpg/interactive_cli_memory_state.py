"""Interactive CLI short-session NPC memory state helpers.

This module is intentionally small and deterministic.  It models only facts that
were explicitly introduced in the current interactive scenario so response
presentation can recall them without claiming durable cross-session memory or
mutating the core simulation contract.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Dict, Mapping

SHORT_SESSION_MEMORY_STATE_VERSION = "interactive_cli_memory_state_v1"
_TRAIL_NAME_RE = re.compile(r"\bmy\s+trail\s+name\s+is\s+([A-Za-z][A-Za-z0-9' -]{1,48})", re.IGNORECASE)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def extract_trail_name(text: str) -> str:
    """Extract a short trail-name fact from a player command."""

    match = _TRAIL_NAME_RE.search(_safe_str(text))
    if not match:
        return ""
    phrase = match.group(1).strip(" .,!?:;\"'")
    parts = phrase.split()
    if len(parts) > 3:
        phrase = " ".join(parts[:3])
    return phrase.strip()


def default_short_session_memory_state() -> Dict[str, Any]:
    """Return an empty short-session memory state."""

    return {
        "version": SHORT_SESSION_MEMORY_STATE_VERSION,
        "remembered_by": {},
        "facts": {},
        "source": "empty_interactive_cli_memory_state",
    }


def normalize_short_session_memory_state(value: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    """Normalize arbitrary memory-state payloads into a deterministic shape."""

    state = deepcopy(_safe_dict(value))
    facts = deepcopy(_safe_dict(state.get("facts")))
    remembered_by = deepcopy(_safe_dict(state.get("remembered_by")))
    trail_name = _safe_str(facts.get("trail_name")).strip()
    if trail_name:
        facts["trail_name"] = trail_name
        remembered_by.setdefault("trail_name", "Bran")
    else:
        facts.pop("trail_name", None)
        remembered_by.pop("trail_name", None)
    return {
        "version": SHORT_SESSION_MEMORY_STATE_VERSION,
        "remembered_by": remembered_by,
        "facts": facts,
        "source": _safe_str(state.get("source") or "interactive_cli_memory_state"),
    }


def extract_short_session_memory_state(turn: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    """Extract memory state from a turn/result payload, falling back to empty state."""

    turn_dict = _safe_dict(turn)
    raw_result = _safe_dict(turn_dict.get("raw_result") or turn_dict.get("result"))
    for candidate in (
        turn_dict.get("interactive_cli_memory_state"),
        raw_result.get("interactive_cli_memory_state"),
        turn_dict.get("memory_state"),
        raw_result.get("memory_state"),
    ):
        if isinstance(candidate, dict):
            return normalize_short_session_memory_state(candidate)
    return default_short_session_memory_state()


def remember_trail_name(state: Mapping[str, Any], trail_name: str, *, npc_name: str = "Bran") -> Dict[str, Any]:
    """Return a new state with a grounded trail-name fact remembered by an NPC."""

    normalized = normalize_short_session_memory_state(state)
    name = _safe_str(trail_name).strip()
    if not name:
        return normalized
    normalized["facts"]["trail_name"] = name
    normalized["remembered_by"]["trail_name"] = _safe_str(npc_name).strip() or "Bran"
    normalized["source"] = "interactive_cli_remember_trail_name_command"
    return normalize_short_session_memory_state(normalized)


def get_trail_name(state: Mapping[str, Any]) -> str:
    return _safe_str(normalize_short_session_memory_state(state)["facts"].get("trail_name")).strip()


def describe_trail_name_ack(state: Mapping[str, Any]) -> tuple[str, str]:
    """Return grounded narration and NPC line for a remembered trail name."""

    trail_name = get_trail_name(state)
    if not trail_name:
        return "Bran listens, but no clear trail name is recorded.", "Tell me the name again and I'll keep it straight."
    return (
        f"Bran records the trail name {trail_name} in this conversation.",
        f"I'll remember it: {trail_name}.",
    )


def describe_trail_name_recall(state: Mapping[str, Any]) -> tuple[str, str]:
    """Return grounded narration and NPC line for recalling a trail name."""

    trail_name = get_trail_name(state)
    if not trail_name:
        return "Bran has no trail name recorded in this conversation.", "You have not given me a trail name to remember yet."
    return (
        f"Bran recalls the trail name from this conversation: {trail_name}.",
        f"You asked me to remember {trail_name}.",
    )
