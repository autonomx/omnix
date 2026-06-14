from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from app.rpg.session.turn_memory_common import (
    DIALOGUE_MEMORY_LIMIT,
    RECENT_TURN_LIMIT,
    bounded,
    d,
    first,
    i,
    memory_state,
    s,
)
from app.rpg.session.turn_memory_writer_helpers import memory_facts, memory_npc


def _turn_entry(
    result: Mapping[str, Any] | None,
    session: Mapping[str, Any] | None,
    player_input: str,
) -> tuple[dict[str, Any], list[dict[str, str]], dict[str, str]]:
    result_dict = d(result)
    runtime = d(d(session).get("runtime_state"))
    sim = d(result_dict.get("simulation_state") or d(session).get("simulation_state"))
    npc = memory_npc(result)
    tick = i(result_dict.get("tick"), i(runtime.get("tick"), 0))
    turn_id = first(result_dict.get("turn_id"), f"turn:{tick}")
    facts = memory_facts(player_input)
    return {
        "id": f"memory-turn:{turn_id}",
        "turn_id": turn_id,
        "tick": tick,
        "player_input": s(player_input)[:500],
        "summary": first(result_dict.get("summary")),
        "location_id": first(sim.get("current_location_id"), sim.get("location_id")),
        "npc_id": npc["id"],
        "npc_speaker": npc["speaker"],
        "npc_line": npc["line"][:500],
        "salience": 0.85 if facts else 0.35,
    }, facts, npc


def _dialogue(turn: Mapping[str, Any], facts: list[dict[str, str]], npc: Mapping[str, str]) -> dict[str, Any]:
    return {
        "id": f"memory-dialogue:{turn['turn_id']}:0",
        "turn_id": str(turn["turn_id"]),
        "tick": i(turn.get("tick")),
        "speaker_id": "player",
        "listener_ids": [npc["id"]] if npc.get("id") else [],
        "location_id": str(turn.get("location_id") or ""),
        "player_text": str(turn.get("player_input") or ""),
        "npc_line": npc.get("line", ""),
        "facts": facts,
        "visibility": "private" if npc.get("id") else "session",
        "salience": 0.9 if facts else 0.6,
    }


def write_turn_memory(
    session: Mapping[str, Any] | None,
    result: Mapping[str, Any] | None,
    *,
    player_input: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    updated = deepcopy(d(session))
    runtime = d(updated.get("runtime_state"))
    memory = memory_state(updated)
    turn, facts, npc = _turn_entry(result, updated, player_input)
    memory["recent_turns"] = bounded([*memory["recent_turns"], turn], RECENT_TURN_LIMIT)
    dialogue = _dialogue(turn, facts, npc) if npc["id"] or facts else None
    if dialogue:
        memory["dialogue_memories"] = bounded(
            [*memory["dialogue_memories"], dialogue],
            DIALOGUE_MEMORY_LIMIT,
        )
    runtime["turn_memory"] = memory
    updated["runtime_state"] = runtime
    return updated, {
        "recent_turn": deepcopy(turn),
        "dialogue_memory": deepcopy(dialogue),
        "facts": deepcopy(facts),
    }
