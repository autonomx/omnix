from __future__ import annotations

from typing import Any, Mapping

from app.rpg.session.turn_memory_common import d, first


def runtime_state(session: Mapping[str, Any] | None, result: Mapping[str, Any] | None) -> dict[str, Any]:
    result_dict = d(result)
    nested = d(result_dict.get("result"))
    return d(result_dict.get("runtime_state") or nested.get("runtime_state") or d(session).get("runtime_state"))


def simulation_state(session: Mapping[str, Any] | None, result: Mapping[str, Any] | None) -> dict[str, Any]:
    result_dict = d(result)
    nested = d(result_dict.get("result"))
    return d(
        result_dict.get("simulation_state")
        or nested.get("simulation_state")
        or d(session).get("simulation_state")
    )


def npc(result: Mapping[str, Any] | None) -> dict[str, str]:
    result_dict = d(result)
    nested = d(result_dict.get("result"))
    visible = d(result_dict.get("visible_response") or nested.get("visible_response"))
    for candidate in (d(result_dict.get("npc")), d(nested.get("npc")), d(visible.get("npc"))):
        speaker = first(candidate.get("speaker"), candidate.get("name"), candidate.get("target_name"))
        npc_id = first(candidate.get("id"), candidate.get("npc_id"), candidate.get("actor_id"))
        line = first(candidate.get("line"), candidate.get("text"), candidate.get("response"))
        if speaker or npc_id or line:
            fallback_id = f"npc:{speaker.lower().replace(' ', '_')}" if speaker else ""
            return {"id": npc_id or fallback_id, "speaker": speaker, "line": line}
    return {"id": "", "speaker": "", "line": ""}


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
        result_dict.get("summary"),
        nested.get("summary"),
        result_dict.get("final_narration"),
        result_dict.get("narration"),
        nested.get("narration"),
        nested.get("outcome"),
    )[:500]
