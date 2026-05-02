from __future__ import annotations

from typing import Any, Dict, List

from tests.rpg.manual.extractors.base import _extract_simulation_state
from tests.rpg.manual.safe import _safe_dict, _safe_list


def _extract_player_inventory(result: Dict[str, Any]) -> Dict[str, Any]:
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
            return candidate

    return {}


def _extract_player_currency(result: Dict[str, Any]) -> Dict[str, Any]:
    inventory_state = _extract_player_inventory(result)

    currency = _safe_dict(inventory_state.get("currency"))
    if currency:
        return currency

    result = _safe_dict(result)
    result_sub = _safe_dict(result.get("result"))
    simulation_state = _extract_simulation_state(result)

    for candidate in [
        result.get("player_currency"),
        result_sub.get("player_currency"),
        simulation_state.get("player_currency"),
        _safe_dict(simulation_state.get("currency_state")).get("player_currency"),
        _safe_dict(simulation_state.get("wallet")).get("currency"),
    ]:
        candidate = _safe_dict(candidate)
        if candidate:
            return candidate

    return {
        "gold": 0,
        "silver": 0,
        "copper": 0,
    }


def _extract_player_items(result: Dict[str, Any]) -> List[Any]:
    inventory_state = _extract_player_inventory(result)
    items = _safe_list(inventory_state.get("items"))
    if items:
        return items

    simulation_state = _extract_simulation_state(result)
    player_state = _safe_dict(simulation_state.get("player_state"))

    for candidate in [
        _safe_dict(simulation_state.get("player_inventory")).get("items"),
        _safe_dict(_safe_dict(simulation_state.get("inventory_state")).get("player_inventory")).get("items"),
        _safe_dict(player_state.get("inventory")).get("items"),
        _safe_dict(player_state.get("inventory_state")).get("items"),
    ]:
        items = _safe_list(candidate)
        if items:
            return items

    return []