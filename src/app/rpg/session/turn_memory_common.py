from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

FORMAT_VERSION = "rpg_turn_memory_contract_v1"
RECENT_TURN_LIMIT = 12
DIALOGUE_MEMORY_LIMIT = 20
RETRIEVAL_LIMIT = 5


def d(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def l(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def s(value: Any) -> str:
    return "" if value is None else str(value)


def i(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def first(*values: Any) -> str:
    for value in values:
        text = s(value).strip()
        if text:
            return text
    return ""


def bounded(values: list[Any], limit: int) -> list[dict[str, Any]]:
    cleaned = [deepcopy(value) for value in values if isinstance(value, Mapping)]
    return cleaned[-max(1, int(limit)) :]


def memory_state(session: Mapping[str, Any] | None) -> dict[str, Any]:
    runtime_state = d(d(session).get("runtime_state"))
    memory = d(runtime_state.get("turn_memory"))
    return {
        "format_version": FORMAT_VERSION,
        "recent_turns": bounded(l(memory.get("recent_turns")), RECENT_TURN_LIMIT),
        "dialogue_memories": bounded(l(memory.get("dialogue_memories")), DIALOGUE_MEMORY_LIMIT),
    }


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
