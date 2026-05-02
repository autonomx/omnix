from __future__ import annotations

from typing import Any, Dict, List

from tests.rpg.manual.extractors.base import _extract_simulation_state
from tests.rpg.manual.safe import _safe_dict, _safe_list


def _extract_active_services(result: Dict[str, Any]) -> List[Any]:
    result = _safe_dict(result)
    result_sub = _safe_dict(result.get("result"))
    resolved_result = _safe_dict(result.get("resolved_result"))
    result_resolved = _safe_dict(result_sub.get("resolved_result"))

    candidates = [
        result.get("active_services"),
        result_sub.get("active_services"),
        resolved_result.get("active_services"),
        result_resolved.get("active_services"),
    ]

    simulation_state = _extract_simulation_state(result)
    service_state = _safe_dict(simulation_state.get("service_state"))
    candidates.extend([
        simulation_state.get("active_services"),
        service_state.get("active_services"),
        service_state.get("services"),
    ])

    session = _safe_dict(result.get("session"))
    session_sim = _safe_dict(session.get("simulation_state"))
    session_service_state = _safe_dict(session_sim.get("service_state"))
    candidates.extend([
        session_sim.get("active_services"),
        session_service_state.get("active_services"),
        session_service_state.get("services"),
    ])

    for candidate in candidates:
        values = _safe_list(candidate)
        if values:
            return values

    return []


def _extract_transaction_history(result: Dict[str, Any]) -> List[Any]:
    result = _safe_dict(result)
    result_sub = _safe_dict(result.get("result"))
    resolved_result = _safe_dict(result.get("resolved_result"))
    result_resolved = _safe_dict(result_sub.get("resolved_result"))

    candidates = [
        result.get("transaction_history"),
        result_sub.get("transaction_history"),
        resolved_result.get("transaction_history"),
        result_resolved.get("transaction_history"),
    ]

    simulation_state = _extract_simulation_state(result)
    service_state = _safe_dict(simulation_state.get("service_state"))
    economy_state = _safe_dict(simulation_state.get("economy_state"))

    candidates.extend([
        simulation_state.get("transaction_history"),
        service_state.get("transaction_history"),
        service_state.get("transactions"),
        economy_state.get("transaction_history"),
        economy_state.get("transactions"),
    ])

    session = _safe_dict(result.get("session"))
    session_sim = _safe_dict(session.get("simulation_state"))
    session_service_state = _safe_dict(session_sim.get("service_state"))
    session_economy_state = _safe_dict(session_sim.get("economy_state"))

    candidates.extend([
        session_sim.get("transaction_history"),
        session_service_state.get("transaction_history"),
        session_service_state.get("transactions"),
        session_economy_state.get("transaction_history"),
        session_economy_state.get("transactions"),
    ])

    for candidate in candidates:
        values = _safe_list(candidate)
        if values:
            return values

    return []


def _extract_service_memories(result: Dict[str, Any]) -> List[Any]:
    result = _safe_dict(result)
    result_sub = _safe_dict(result.get("result"))
    resolved_result = _safe_dict(result.get("resolved_result"))
    result_resolved = _safe_dict(result_sub.get("resolved_result"))

    candidates = [
        result.get("service_memories"),
        result_sub.get("service_memories"),
        resolved_result.get("service_memories"),
        result_resolved.get("service_memories"),
    ]

    simulation_state = _extract_simulation_state(result)
    service_state = _safe_dict(simulation_state.get("service_state"))
    memory_state = _safe_dict(simulation_state.get("memory_state"))
    companion_memory_state = _safe_dict(simulation_state.get("companion_memory_state"))

    candidates.extend([
        simulation_state.get("service_memories"),
        service_state.get("service_memories"),
        service_state.get("memories"),
        memory_state.get("service_memories"),
        memory_state.get("memories"),
        companion_memory_state.get("service_memories"),
    ])

    session = _safe_dict(result.get("session"))
    session_sim = _safe_dict(session.get("simulation_state"))
    session_service_state = _safe_dict(session_sim.get("service_state"))
    session_memory_state = _safe_dict(session_sim.get("memory_state"))
    session_companion_memory_state = _safe_dict(session_sim.get("companion_memory_state"))

    candidates.extend([
        session_sim.get("service_memories"),
        session_service_state.get("service_memories"),
        session_service_state.get("memories"),
        session_memory_state.get("service_memories"),
        session_memory_state.get("memories"),
        session_companion_memory_state.get("service_memories"),
    ])

    for candidate in candidates:
        values = _safe_list(candidate)
        if values:
            return values

    return []