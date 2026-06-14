from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Mapping

from app.rpg.session.turn_memory_common import DIALOGUE_MEMORY_LIMIT, RECENT_TURN_LIMIT, bounded, d, first, i, memory_state, s

_ALIAS_RE = re.compile(r"\b(?:my\s+)?(?P<key>trail\s+name|name)\s+is\s+(?P<value>[A-Za-z][A-Za-z0-9' -]{0,40})", re.I)


def _facts(text: str) -> list[dict[str, str]]:
    match = _ALIAS_RE.search(s(text))
    if not match:
        return []
    value = re.split(r"\s+(?:and|but|because|when|while)\s+", match.group("value"))[0]
    value = value.strip().strip(".?!,;:\"'")[:48]
    key = "trail_name" if "trail" in match.group("key").lower() else "name"
    return [{"type": "identity_alias", "subject": "player", "key": key, "value": value}] if value else []


def _npc(result: Mapping[str, Any] | None) -> dict[str, str]:
    result_dict, nested = d(result), d(d(result).get("result"))
    for candidate in (d(result_dict.get("npc")), d(nested.get("npc"))):
        speaker = first(candidate.get("speaker"), candidate.get("name"))
        npc_id = first(candidate.get("id"), candidate.get("npc_id"))
        if speaker or npc_id:
            return {"id": npc_id or f"npc:{speaker.lower()}", "speaker": speaker, "line": first(candidate.get("line"), candidate.get("text"))}
    return {"id": "", "speaker": "", "line": ""}


def write_turn_memory(session: Mapping[str, Any] | None, result: Mapping[str, Any] | None, *, player_input: str) -> tuple[dict[str, Any], dict[str, Any]]:
    updated = deepcopy(d(session)); runtime = d(updated.get("runtime_state")); memory = memory_state(updated)
    result_dict, sim, npc = d(result), d(d(result).get("simulation_state") or d(session).get("simulation_state")), _npc(result)
    tick = i(result_dict.get("tick"), i(runtime.get("tick"), 0)); turn_id = first(result_dict.get("turn_id"), f"turn:{tick}")
    facts = _facts(player_input)
    turn = {"id": f"memory-turn:{turn_id}", "turn_id": turn_id, "tick": tick, "player_input": s(player_input)[:500], "summary": first(result_dict.get("summary")), "location_id": first(sim.get("current_location_id"), sim.get("location_id")), "npc_id": npc["id"], "npc_speaker": npc["speaker"], "npc_line": npc["line"][:500], "salience": 0.85 if facts else 0.35}
    memory["recent_turns"] = bounded([*memory["recent_turns"], turn], RECENT_TURN_LIMIT)
    dialogue = None
    if npc["id"] or facts:
        dialogue = {"id": f"memory-dialogue:{turn_id}:0", "turn_id": turn_id, "tick": tick, "speaker_id": "player", "listener_ids": [npc["id"]] if npc["id"] else [], "location_id": turn["location_id"], "player_text": s(player_input), "npc_line": npc["line"], "facts": facts, "visibility": "private" if npc["id"] else "session", "salience": 0.9 if facts else 0.6}
        memory["dialogue_memories"] = bounded([*memory["dialogue_memories"], dialogue], DIALOGUE_MEMORY_LIMIT)
    runtime["turn_memory"] = memory; updated["runtime_state"] = runtime
    return updated, {"recent_turn": deepcopy(turn), "dialogue_memory": deepcopy(dialogue), "facts": deepcopy(facts)}
