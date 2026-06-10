"""Interactive CLI equipment state helpers.

This module is intentionally small and deterministic.  It models the short-session
inventory/equipment facts that the interactive feature matrix needs without claiming
full RPG inventory persistence or changing the core simulation contract.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, Mapping, Sequence

EQUIPMENT_STATE_VERSION = "interactive_cli_equipment_state_v1"
DEFAULT_CARRIED_ITEMS: tuple[str, ...] = ("sword", "shield", "ration", "waterskin")
READYABLE_ITEMS: tuple[str, ...] = ("sword", "shield")


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _dedupe_lower(values: Iterable[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = _safe_str(value).strip().lower()
        if item and item not in seen:
            out.append(item)
            seen.add(item)
    return out


def default_equipment_state() -> Dict[str, Any]:
    """Return the starter interactive equipment state used by feature probes."""

    return {
        "version": EQUIPMENT_STATE_VERSION,
        "carried_items": list(DEFAULT_CARRIED_ITEMS),
        "readied_items": [],
        "source": "starter_interactive_cli_equipment_state",
    }


def normalize_equipment_state(value: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    """Normalize an arbitrary equipment-state payload into a deterministic shape."""

    state = deepcopy(_safe_dict(value))
    carried = _dedupe_lower(state.get("carried_items") or DEFAULT_CARRIED_ITEMS)
    if not carried:
        carried = list(DEFAULT_CARRIED_ITEMS)
    readied = [item for item in _dedupe_lower(state.get("readied_items") or []) if item in carried]
    return {
        "version": EQUIPMENT_STATE_VERSION,
        "carried_items": carried,
        "readied_items": readied,
        "source": _safe_str(state.get("source") or "interactive_cli_equipment_state"),
    }


def extract_equipment_state(turn: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    """Extract equipment state from a turn/result payload, falling back to defaults."""

    turn_dict = _safe_dict(turn)
    raw_result = _safe_dict(turn_dict.get("raw_result") or turn_dict.get("result"))
    for candidate in (
        turn_dict.get("interactive_cli_equipment_state"),
        raw_result.get("interactive_cli_equipment_state"),
        turn_dict.get("equipment_state"),
        raw_result.get("equipment_state"),
    ):
        if isinstance(candidate, dict):
            return normalize_equipment_state(candidate)
    return default_equipment_state()


def apply_ready_command(state: Mapping[str, Any], requested_items: Sequence[str] = READYABLE_ITEMS) -> Dict[str, Any]:
    """Return a new state with requested carried items marked as readied."""

    normalized = normalize_equipment_state(state)
    carried = set(normalized["carried_items"])
    readied = set(normalized["readied_items"])
    for item in requested_items:
        lowered = _safe_str(item).strip().lower()
        if lowered in carried:
            readied.add(lowered)
    normalized["readied_items"] = [item for item in normalized["carried_items"] if item in readied]
    normalized["source"] = "interactive_cli_ready_equipment_command"
    return normalized


def describe_inventory(state: Mapping[str, Any]) -> str:
    normalized = normalize_equipment_state(state)
    carried = ", ".join(normalized["carried_items"])
    readied = ", ".join(normalized["readied_items"])
    if readied:
        return f"You are carrying {carried}. Readied gear: {readied}."
    return f"You are carrying {carried}. Nothing is readied yet."


def describe_ready_change(before: Mapping[str, Any], after: Mapping[str, Any]) -> str:
    before_state = normalize_equipment_state(before)
    after_state = normalize_equipment_state(after)
    newly_readied = [item for item in after_state["readied_items"] if item not in before_state["readied_items"]]
    if newly_readied:
        ready_text = " and ".join(newly_readied)
        return f"You ready your {ready_text}. Readied gear now: {', '.join(after_state['readied_items'])}."
    if after_state["readied_items"]:
        return f"Your readied gear remains: {', '.join(after_state['readied_items'])}."
    return "You check your gear, but nothing new is readied."
