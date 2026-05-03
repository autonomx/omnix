from __future__ import annotations

from typing import Any, Dict, List

from tests.rpg.manual.safe import _safe_dict, _safe_list
from tests.rpg.manual.summary_sanitizer import (
    compact_result_for_summary as _sanitizer_compact_result,
    sanitize_scenario_summary,
)


def _extract_simulation_state(result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract simulation state from result, preferring fresh result data over session metadata."""
    result = _safe_dict(result)
    result_sub = _safe_dict(result.get("result"))

    # Prefer fresh result state
    if result_sub:
        simulation_state = {}
        # Collect all the state keys from result
        state_keys = [
            "memory_state", "relationship_state", "npc_emotion_state", "service_offer_state",
            "journal_state", "world_event_state", "quest_state", "location_state",
            "travel_result", "conversation_thread_state", "npc_reputation_state",
            "conversation_rumor_state", "present_npc_state", "player_state"
        ]
        for key in state_keys:
            value = result_sub.get(key)
            if value is not None:
                simulation_state[key] = value
        if simulation_state:
            return simulation_state

    # Fall back to session metadata
    session = _safe_dict(result.get("session"))
    setup_payload = _safe_dict(session.get("setup_payload"))
    metadata = _safe_dict(setup_payload.get("metadata"))
    return _safe_dict(metadata.get("simulation_state"))


def _extract_player_inventory(result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract player inventory from tolerant manual/runtime result shapes."""
    result = _safe_dict(result)
    result_sub = _safe_dict(result.get("result"))
    resolved_result = _safe_dict(result.get("resolved_result"))
    result_resolved = _safe_dict(result_sub.get("resolved_result"))

    candidates = [
        result.get("player_inventory"),
        result_sub.get("player_inventory"),
        resolved_result.get("player_inventory"),
        result_resolved.get("player_inventory"),
    ]

    simulation_state = _extract_simulation_state(result)
    player_state = _safe_dict(simulation_state.get("player_state"))

    candidates.extend([
        simulation_state.get("player_inventory"),
        _safe_dict(simulation_state.get("inventory_state")).get("player_inventory"),
        player_state.get("player_inventory"),
        player_state.get("inventory"),
        player_state.get("inventory_state"),
    ])

    session = _safe_dict(result.get("session"))
    session_sim = _safe_dict(session.get("simulation_state"))
    session_player_state = _safe_dict(session_sim.get("player_state"))
    candidates.extend([
        session_sim.get("player_inventory"),
        _safe_dict(session_sim.get("inventory_state")).get("player_inventory"),
        session_player_state.get("player_inventory"),
        session_player_state.get("inventory"),
        session_player_state.get("inventory_state"),
    ])

    for candidate in candidates:
        candidate = _safe_dict(candidate)
        if candidate:
            # Old shapes sometimes store {"currency": ..., "items": ...}; new
            # L1-L3 shapes often store {"items": ..., "equipment": ...}.
            return candidate

    return {}


def _extract_service_memories(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract service memories from result for contamination checking."""
    simulation_state = _extract_simulation_state(result)
    service_state = _safe_dict(simulation_state.get("service_state"))
    memories = _safe_list(service_state.get("memories"))
    if memories:
        return memories
    # Fallback to other possible locations
    return _safe_list(_safe_dict(result.get("result")).get("service_memories"))


def _pre_turn_contamination_snapshot(simulation_state: Dict[str, Any]) -> Dict[str, int]:
    """Capture pre-turn state counts used by scenario contamination checks.

    This helper is intentionally tolerant because many manual scenarios seed only
    partial simulation_state. Missing sections should count as zero rather than
    crashing the run.
    """
    simulation_state = _safe_dict(simulation_state)
    if not simulation_state:
        return {
            "transaction_history_count": 0,
            "active_services_count": 0,
            "journal_entry_count": 0,
            "world_event_count": 0,
            "quest_count": 0,
        }

    journal_state = _safe_dict(simulation_state.get("journal_state"))
    world_event_state = _safe_dict(simulation_state.get("world_event_state"))
    quest_state = _safe_dict(simulation_state.get("quest_state"))

    # Some newer bundles store world events directly on simulation_state.
    world_events = _safe_list(world_event_state.get("events"))
    if not world_events:
        world_events = _safe_list(simulation_state.get("world_events"))

    quests = _safe_list(quest_state.get("quests"))
    if not quests:
        quests = _safe_list(simulation_state.get("quests"))

    return {
        "transaction_history_count": len(_safe_list(simulation_state.get("transaction_history"))),
        "active_services_count": len(_safe_list(simulation_state.get("active_services"))),
        "journal_entry_count": len(_safe_list(journal_state.get("entries"))),
        "world_event_count": len(world_events),
        "quest_count": len(quests),
    }


def _compact_result_for_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    """Compact a turn result for summary by removing large state blobs.

    This is now a thin wrapper around the more comprehensive sanitizer function.
    """
    return _sanitizer_compact_result(result)


def _build_service_summary_row(
    *,
    scenario_name: str,
    session_id: str,
    seeded_currency: Dict[str, Any],
    turns: List[Dict[str, Any]],
    sanitize: bool = True,
) -> Dict[str, Any]:
    """Build a summary row for a service scenario run.

    Args:
        sanitize: If True, apply summary sanitizer to reduce artifact bloat.
    """
    summary = {
        "scenario": scenario_name,
        "session_id": session_id,
        "seeded_currency": seeded_currency,
        "turns": turns,
    }

    # Aggregate warnings from turns
    all_scenario_warnings = []
    all_regression_warnings = []

    for turn in turns:
        turn = _safe_dict(turn)
        all_scenario_warnings.extend(_safe_list(turn.get("scenario_warnings")))
        all_regression_warnings.extend(_safe_list(turn.get("regression_warnings")))

    if all_scenario_warnings:
        summary["scenario_warnings"] = all_scenario_warnings
    if all_regression_warnings:
        summary["regression_warnings"] = all_regression_warnings

    # Check if any turn has an error
    for turn in turns:
        if _safe_dict(turn.get("result") or {}).get("error"):
            summary["error"] = "turn_error"
            break

    # Apply sanitization to reduce artifact bloat
    if sanitize:
        return sanitize_scenario_summary(summary)

    return summary
