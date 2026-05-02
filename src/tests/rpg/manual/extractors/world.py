from __future__ import annotations

from typing import Any, Dict, List

from tests.rpg.manual.extractors.base import _extract_simulation_state
from tests.rpg.manual.safe import _safe_dict, _safe_list


def _extract_memory_rumors(result: Dict[str, Any]) -> List[Any]:
    result = _safe_dict(result)
    result_sub = _safe_dict(result.get("result"))
    resolved_result = _safe_dict(result.get("resolved_result"))
    result_resolved = _safe_dict(result_sub.get("resolved_result"))

    candidates = [
        result.get("memory_rumors"),
        result_sub.get("memory_rumors"),
        resolved_result.get("memory_rumors"),
        result_resolved.get("memory_rumors"),
        result.get("rumors"),
        result_sub.get("rumors"),
        resolved_result.get("rumors"),
        result_resolved.get("rumors"),
    ]

    simulation_state = _extract_simulation_state(result)
    memory_state = _safe_dict(simulation_state.get("memory_state"))
    rumor_state = _safe_dict(simulation_state.get("rumor_state"))
    living_world_state = _safe_dict(simulation_state.get("living_world_state"))

    candidates.extend([
        simulation_state.get("memory_rumors"),
        simulation_state.get("rumors"),
        memory_state.get("rumors"),
        memory_state.get("memory_rumors"),
        rumor_state.get("rumors"),
        rumor_state.get("active_rumors"),
        living_world_state.get("rumors"),
        living_world_state.get("active_rumors"),
    ])

    session = _safe_dict(result.get("session"))
    session_sim = _safe_dict(session.get("simulation_state"))
    session_memory_state = _safe_dict(session_sim.get("memory_state"))
    session_rumor_state = _safe_dict(session_sim.get("rumor_state"))
    session_living_world_state = _safe_dict(session_sim.get("living_world_state"))

    candidates.extend([
        session_sim.get("memory_rumors"),
        session_sim.get("rumors"),
        session_memory_state.get("rumors"),
        session_memory_state.get("memory_rumors"),
        session_rumor_state.get("rumors"),
        session_rumor_state.get("active_rumors"),
        session_living_world_state.get("rumors"),
        session_living_world_state.get("active_rumors"),
    ])

    for candidate in candidates:
        values = _safe_list(candidate)
        if values:
            return values

    return []