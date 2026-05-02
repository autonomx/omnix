from __future__ import annotations

from typing import Any, Dict

from tests.rpg.manual.safe import _safe_dict, _safe_list, _safe_str


def _extract_nested_dict_by_key(value: Any, key: str, *, max_depth: int = 8) -> Dict[str, Any]:
    seen: set[int] = set()

    def walk(node: Any, depth: int) -> Dict[str, Any]:
        if depth > max_depth:
            return {}
        if not isinstance(node, (dict, list)):
            return {}

        node_id = id(node)
        if node_id in seen:
            return {}
        seen.add(node_id)

        if isinstance(node, dict):
            direct = _safe_dict(node.get(key))
            if direct:
                return direct
            for nested in node.values():
                found = walk(nested, depth + 1)
                if found:
                    return found

        if isinstance(node, list):
            for nested in node:
                found = walk(nested, depth + 1)
                if found:
                    return found

        return {}

    return walk(value, 0)


def _first_dict(*values: Any) -> Dict[str, Any]:
    for value in values:
        value = _safe_dict(value)
        if value:
            return value
    return {}


def _first_list(*values: Any) -> List[Any]:
    for value in values:
        value = _safe_list(value)
        if value:
            return value
    return []


# Move the existing implementations from manual_llm_transcript.py:
def _extract_turn_contract(result: Dict[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(result)
    payload = _safe_dict(result.get("result") or result)
    contract = _safe_dict(payload.get("turn_contract"))
    if contract:
        return contract

    session = _safe_dict(result.get("session"))
    runtime_state = _safe_dict(session.get("runtime_state"))
    return _safe_dict(runtime_state.get("last_turn_contract"))


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


def _extract_session(result: Dict[str, Any]) -> Dict[str, Any]:
    return _safe_dict(
        result.get("session")
        or _safe_dict(result.get("result")).get("session")
    )


def _extract_visible_interaction_reason(result: Dict[str, Any]) -> str:
    result = _safe_dict(result)
    result_sub = _safe_dict(result.get("result"))
    nested_result = _safe_dict(result_sub.get("result"))
    turn_contract = _extract_turn_contract(result)
    resolved = _safe_dict(
        turn_contract.get("resolved_result")
        or turn_contract.get("resolved_action")
    )

    candidates = [
        result.get("visible_interaction_reason"),
        result_sub.get("visible_interaction_reason"),
        nested_result.get("visible_interaction_reason"),
        turn_contract.get("visible_interaction_reason"),
        resolved.get("visible_interaction_reason"),
    ]

    interaction = _extract_interaction_result(result)
    for key in ("inventory_result", "container_result", "repair_result"):
        nested = _safe_dict(interaction.get(key))
        if _safe_str(nested.get("reason")):
            candidates.append(nested.get("reason"))

    if _safe_str(interaction.get("reason")):
        candidates.append(interaction.get("reason"))

    for candidate in candidates:
        candidate = _safe_str(candidate)
        if candidate:
            return candidate

    contract = _extract_combat_narration_contract(result)
    raw_combat = _safe_dict(contract.get("raw_combat_result"))
    if _safe_str(raw_combat.get("reason")):
        return _safe_str(raw_combat.get("reason"))

    return ""


def _extract_current_location_id(result: Dict[str, Any]) -> str:
    """Extract the player's current location from a tolerant set of result shapes.

    Manual scenario result payloads vary by subsystem. Missing location data
    should produce an empty string, not crash the whole scenario run.
    """
    result = _safe_dict(result)
    result_sub = _safe_dict(result.get("result"))

    for candidate in [
        result.get("current_location_id"),
        result_sub.get("current_location_id"),
        _safe_dict(result.get("resolved_result")).get("current_location_id"),
        _safe_dict(result_sub.get("resolved_result")).get("current_location_id"),
    ]:
        text = _safe_str(candidate).strip()
        if text:
            return text

    location_state = _extract_location_state(result)
    for key in ["current_location_id", "location_id", "player_location_id"]:
        text = _safe_str(location_state.get(key)).strip()
        if text:
            return text

    service_debug = _extract_service_debug(result)
    service_result = _safe_dict(service_debug.get("service_result"))
    for key in ["current_location_id", "location_id", "player_location_id"]:
        text = _safe_str(service_result.get(key)).strip()
        if text:
            return text

    travel_result = _extract_travel_result(result)
    for key in ["to_location_id", "from_location_id", "current_location_id"]:
        text = _safe_str(travel_result.get(key)).strip()
        if text:
            return text

    simulation_state = _extract_simulation_state(result)
    player_state = _safe_dict(simulation_state.get("player_state"))

    for candidate in [
        player_state.get("location_id"),
        player_state.get("current_location_id"),
        simulation_state.get("player_location_id"),
        simulation_state.get("location_id"),
        simulation_state.get("current_location_id"),
    ]:
        text = _safe_str(candidate).strip()
        if text:
            return text

    return ""


def _extract_interaction_result(result: Dict[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(result)
    result_sub = _safe_dict(result.get("result"))
    nested_result = _safe_dict(result_sub.get("result"))
    resolved_result = _safe_dict(result.get("resolved_result"))
    result_resolved = _safe_dict(result_sub.get("resolved_result"))

    turn_contract = _extract_turn_contract(result)
    contract_resolved = _safe_dict(
        turn_contract.get("resolved_result")
        or turn_contract.get("resolved_action")
    )

    candidates = [
        result.get("general_interaction_result"),
        result_sub.get("general_interaction_result"),
        nested_result.get("general_interaction_result"),
        resolved_result.get("general_interaction_result"),
        result_resolved.get("general_interaction_result"),
        turn_contract.get("general_interaction_result"),
        contract_resolved.get("general_interaction_result"),
        result.get("interaction_result"),
        result_sub.get("interaction_result"),
        nested_result.get("interaction_result"),
        resolved_result.get("interaction_result"),
        result_resolved.get("interaction_result"),
        turn_contract.get("interaction_result"),
        contract_resolved.get("interaction_result"),
    ]

    for candidate in candidates:
        candidate = _safe_dict(candidate)
        if candidate:
            return candidate

    return {}