from __future__ import annotations

from typing import Any, Mapping

from app.rpg.session.turn_memory_common import d, first
from app.rpg.session.turn_memory_npc_extractors import npc


def runtime_state(session: Mapping[str, Any] | None, result: Mapping[str, Any] | None) -> dict[str, Any]:
    result_dict = d(result)
    nested = d(result_dict.get("result"))
    return d(result_dict.get("runtime_state") or nested.get("runtime_state") or d(session).get("runtime_state"))


def simulation_state(session: Mapping[str, Any] | None, result: Mapping[str, Any] | None) -> dict[str, Any]:
    result_dict = d(result)
    nested = d(result_dict.get("result"))
    return d(result_dict.get("simulation_state") or nested.get("simulation_state") or d(session).get("simulation_state"))


def action_type(result: Mapping[str, Any] | None) -> str:
    result_dict = d(result)
    nested = d(result_dict.get("result"))
    return first(
        result_dict.get("action_type"),
        nested.get("action_type"),
        result_dict.get("semantic_action_type"),
        nested.get("semantic_action_type"),
        result_dict.get("outcome"),
        nested.get("outcome"),
    )


def summary(result: Mapping[str, Any] | None) -> str:
    result_dict = d(result)
    nested = d(result_dict.get("result"))
    return first(
        result_dict.get("summary"), nested.get("summary"), result_dict.get("final_narration"), result_dict.get("narration"),
        nested.get("narration"), nested.get("outcome"),
    )[:500]
