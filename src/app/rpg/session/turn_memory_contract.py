from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Mapping

FORMAT_VERSION = "rpg_turn_memory_contract_v1"
RECENT_TURN_LIMIT = 12
DIALOGUE_MEMORY_LIMIT = 20
RETRIEVAL_LIMIT = 5

_TRAIL_NAME_RE = re.compile(r"\b(?:my\s+)?trail\s+name\s+is\s+([A-Za-z][A-Za-z0-9' -]{0,40})", re.IGNORECASE)
_NAME_RE = re.compile(r"\bmy\s+name\s+is\s+([A-Za-z][A-Za-z0-9' -]{0,40})", re.IGNORECASE)


def _d(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _l(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _s(value: Any) -> str:
    return "" if value is None else str(value)


def _i(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _first(*values: Any) -> str:
    for value in values:
        text = _s(value).strip()
        if text:
            return text
    return ""


def _bounded(values: list[Any], limit: int) -> list[dict[str, Any]]:
    return [deepcopy(value) for value in values if isinstance(value, Mapping)][-max(1, int(limit)) :]


def _memory_state(session: Mapping[str, Any] | None) -> dict[str, Any]:
    runtime_state = _d(_d(session).get("runtime_state"))
    memory = _d(runtime_state.get("turn_memory"))
    return {
        "format_version": FORMAT_VERSION,
        "recent_turns": _bounded(_l(memory.get("recent_turns")), RECENT_TURN_LIMIT),
        "dialogue_memories": _bounded(_l(memory.get("dialogue_memories")), DIALOGUE_MEMORY_LIMIT),
    }


def _runtime_state(session: Mapping[str, Any] | None, result: Mapping[str, Any] | None) -> dict[str, Any]:
    result_dict = _d(result)
    nested = _d(result_dict.get("result"))
    return _d(result_dict.get("runtime_state") or nested.get("runtime_state") or _d(session).get("runtime_state"))


def _simulation_state(session: Mapping[str, Any] | None, result: Mapping[str, Any] | None) -> dict[str, Any]:
    result_dict = _d(result)
    nested = _d(result_dict.get("result"))
    return _d(result_dict.get("simulation_state") or nested.get("simulation_state") or _d(session).get("simulation_state"))


def _npc(result: Mapping[str, Any] | None) -> dict[str, str]:
    result_dict = _d(result)
    nested = _d(result_dict.get("result"))
    visible = _d(result_dict.get("visible_response") or nested.get("visible_response"))
    for candidate in (_d(result_dict.get("npc")), _d(nested.get("npc")), _d(visible.get("npc"))):
        speaker = _first(candidate.get("speaker"), candidate.get("name"), candidate.get("target_name"))
        npc_id = _first(candidate.get("id"), candidate.get("npc_id"), candidate.get("actor_id"))
        line = _first(candidate.get("line"), candidate.get("text"), candidate.get("response"))
        if speaker or npc_id or line:
            return {"id": npc_id or f"npc:{speaker.lower().replace(' ', '_')}", "speaker": speaker, "line": line}
    return {"id": "", "speaker": "", "line": ""}


def _action_type(result: Mapping[str, Any] | None) -> str:
    result_dict = _d(result)
    nested = _d(result_dict.get("result"))
    return _first(
        result_dict.get("action_type"),
        nested.get("action_type"),
        result_dict.get("semantic_action_type"),
        nested.get("semantic_action_type"),
        result_dict.get("outcome"),
        nested.get("outcome"),
    )


def _summary(result: Mapping[str, Any] | None) -> str:
    result_dict = _d(result)
    nested = _d(result_dict.get("result"))
    return _first(
        result_dict.get("summary"),
        nested.get("summary"),
        result_dict.get("final_narration"),
        result_dict.get("narration"),
        nested.get("narration"),
        nested.get("outcome"),
    )[:500]


def _clean_fact(value: str) -> str:
    text = value.strip().strip(".?!,;:\"'")
    lower = text.lower()
    cut = len(text)
    for stop in (" and ", " but ", " because ", " when ", " while "):
        index = lower.find(stop)
        if index >= 0:
            cut = min(cut, index)
    return text[:cut].strip().strip(".?!,;:\"'")[:48]


def extract_player_memory_facts(player_input: str) -> list[dict[str, str]]:
    facts: list[dict[str, str]] = []
    trail = _TRAIL_NAME_RE.search(_s(player_input))
    if trail:
        value = _clean_fact(trail.group(1))
        if value:
            facts.append({"type": "identity_alias", "subject": "player", "key": "trail_name", "value": value})
    name = _NAME_RE.search(_s(player_input))
    if name:
        value = _clean_fact(name.group(1))
        if value:
            facts.append({"type": "identity_alias", "subject": "player", "key": "name", "value": value})
    return facts


def _topic_tags(player_input: str, action_type: str, facts: list[dict[str, str]]) -> list[str]:
    text = f"{player_input} {action_type}".lower()
    tags: set[str] = set()
    if facts or any(term in text for term in ("remember", "name", "called", "trail name")):
        tags.add("identity")
    if any(term in text for term in ("rumor", "rumour", "gossip", "heard")):
        tags.add("rumor")
    if any(term in text for term in ("bandit", "road", "quarry", "clue")):
        tags.add("quest_clue")
    if any(term in text for term in ("buy", "sell", "price", "silver", "gold", "room", "ration")):
        tags.add("commerce")
    if "dialogue" in action_type.lower() or "npc" in action_type.lower():
        tags.add("dialogue")
    return sorted(tags)


def build_turn_memory_entry(*, session: Mapping[str, Any] | None, result: Mapping[str, Any] | None, player_input: str) -> dict[str, Any]:
    runtime_state = _runtime_state(session, result)
    simulation_state = _simulation_state(session, result)
    result_dict = _d(result)
    tick = _i(result_dict.get("tick"), _i(runtime_state.get("tick"), 0))
    turn_id = _first(result_dict.get("turn_id"), f"turn:{tick}")
    action_type = _action_type(result)
    npc = _npc(result)
    facts = extract_player_memory_facts(player_input)
    return {
        "id": f"memory-turn:{turn_id}",
        "turn_id": turn_id,
        "tick": tick,
        "player_input": _s(player_input).strip()[:500],
        "action_type": action_type,
        "summary": _summary(result),
        "location_id": _first(simulation_state.get("current_location_id"), simulation_state.get("location_id")),
        "location_name": _first(simulation_state.get("location_name"), simulation_state.get("current_location_name")),
        "npc_id": npc["id"],
        "npc_speaker": npc["speaker"],
        "npc_line": npc["line"][:500],
        "topic_tags": _topic_tags(player_input, action_type, facts),
        "salience": 0.85 if facts else (0.65 if npc["speaker"] else 0.35),
        "source": "deterministic_turn_memory_writer_v1",
    }


def _dialogue_entry(turn_entry: Mapping[str, Any], facts: list[dict[str, str]]) -> dict[str, Any]:
    npc_id = _s(turn_entry.get("npc_id"))
    npc_speaker = _s(turn_entry.get("npc_speaker"))
    listener_id = npc_id or (f"npc:{npc_speaker.lower().replace(' ', '_')}" if npc_speaker else "")
    return {
        "id": f"memory-dialogue:{_s(turn_entry.get('turn_id'))}:{len(facts)}",
        "turn_id": _s(turn_entry.get("turn_id")),
        "tick": _i(turn_entry.get("tick"), 0),
        "speaker_id": "player",
        "listener_ids": [listener_id] if listener_id else [],
        "listener_names": [npc_speaker] if npc_speaker else [],
        "location_id": _s(turn_entry.get("location_id")),
        "player_text": _s(turn_entry.get("player_input")),
        "npc_line": _s(turn_entry.get("npc_line")),
        "summary": _first(turn_entry.get("summary"), f"Player spoke with {npc_speaker}." if npc_speaker else "Player had a dialogue exchange."),
        "facts": deepcopy(facts),
        "topic_tags": _l(turn_entry.get("topic_tags")),
        "visibility": "private" if listener_id else "session",
        "salience": 0.9 if facts else 0.6,
        "source": "deterministic_dialogue_memory_writer_v1",
    }


def _is_dialogue(player_input: str, result: Mapping[str, Any] | None, facts: list[dict[str, str]]) -> bool:
    npc = _npc(result)
    action_type = _action_type(result).lower()
    return bool(npc["speaker"] or npc["line"] or facts or "dialogue" in action_type or "npc" in action_type)


def _query_tokens(player_input: str) -> set[str]:
    stop = {"the", "and", "you", "your", "what", "about", "tell", "me", "do", "did", "can", "i", "a", "an", "is", "are"}
    return {token for token in re.findall(r"[a-z0-9']+", _s(player_input).lower()) if len(token) >= 3 and token not in stop}


def _visible_to(entry: Mapping[str, Any], addressed_actor_id: str) -> bool:
    if _s(entry.get("visibility")) != "private" or not addressed_actor_id:
        return True
    allowed = {_s(value) for value in _l(entry.get("listener_ids")) if _s(value)} | {_s(entry.get("speaker_id"))}
    return addressed_actor_id in allowed


def retrieve_relevant_memories(memory: Mapping[str, Any], *, player_input: str, addressed_actor_id: str = "", location_id: str = "", limit: int = RETRIEVAL_LIMIT) -> list[dict[str, Any]]:
    tokens = _query_tokens(player_input)
    wants_recall = any(term in _s(player_input).lower() for term in ("remember", "name", "called", "trail name", "what did i"))
    scored: list[tuple[float, dict[str, Any]]] = []
    for entry in _bounded(_l(_d(memory).get("dialogue_memories")), DIALOGUE_MEMORY_LIMIT):
        if not _visible_to(entry, addressed_actor_id):
            continue
        haystack = " ".join(
            [
                _s(entry.get("player_text")),
                _s(entry.get("summary")),
                _s(entry.get("npc_line")),
                " ".join(_s(tag) for tag in _l(entry.get("topic_tags"))),
                " ".join(_s(fact.get("value")) for fact in _l(entry.get("facts")) if isinstance(fact, Mapping)),
            ]
        ).lower()
        score = float(entry.get("salience") or 0.0) + sum(1 for token in tokens if token in haystack) * 0.4
        if wants_recall and _l(entry.get("facts")):
            score += 2.0
        if addressed_actor_id and addressed_actor_id in {_s(value) for value in _l(entry.get("listener_ids"))}:
            score += 1.5
        if location_id and location_id == _s(entry.get("location_id")):
            score += 0.5
        if score > 0.0:
            scored.append((score, entry))
    scored.sort(key=lambda item: (-item[0], -_i(item[1].get("tick"), 0), _s(item[1].get("id"))))
    return [dict(entry, retrieval_score=round(score, 3)) for score, entry in scored[: max(1, int(limit))]]


def write_turn_memory(session: Mapping[str, Any] | None, result: Mapping[str, Any] | None, *, player_input: str) -> tuple[dict[str, Any], dict[str, Any]]:
    updated_session = deepcopy(_d(session))
    runtime_state = _d(updated_session.get("runtime_state"))
    memory = _memory_state(updated_session)
    turn_entry = build_turn_memory_entry(session=updated_session, result=result, player_input=player_input)
    facts = extract_player_memory_facts(player_input)
    memory["recent_turns"] = _bounded([*memory["recent_turns"], turn_entry], RECENT_TURN_LIMIT)
    written: dict[str, Any] = {"recent_turn": deepcopy(turn_entry), "dialogue_memory": None, "facts": deepcopy(facts)}
    if _is_dialogue(player_input, result, facts):
        dialogue_entry = _dialogue_entry(turn_entry, facts)
        memory["dialogue_memories"] = _bounded([*memory["dialogue_memories"], dialogue_entry], DIALOGUE_MEMORY_LIMIT)
        written["dialogue_memory"] = deepcopy(dialogue_entry)
    runtime_state["turn_memory"] = memory
    updated_session["runtime_state"] = runtime_state
    return updated_session, written


def attach_turn_memory_context_with_session(result: Mapping[str, Any], *, session: Mapping[str, Any] | None, player_input: str) -> tuple[dict[str, Any], dict[str, Any]]:
    updated_session, written = write_turn_memory(session, result, player_input=player_input)
    memory = _memory_state(updated_session)
    turn_entry = _d(written.get("recent_turn"))
    retrieved = retrieve_relevant_memories(
        memory,
        player_input=player_input,
        addressed_actor_id=_s(turn_entry.get("npc_id")),
        location_id=_s(turn_entry.get("location_id")),
    )
    payload = {
        "format_version": FORMAT_VERSION,
        "written": written,
        "retrieved": retrieved,
        "recent_turn_count": len(_l(memory.get("recent_turns"))),
        "dialogue_memory_count": len(_l(memory.get("dialogue_memories"))),
        "state_path": "runtime_state.turn_memory",
        "deterministic": True,
        "presentation_only": True,
    }
    updated_result = deepcopy(_d(result))
    updated_result["turn_memory"] = deepcopy(payload)
    nested = _d(updated_result.get("result"))
    if nested:
        nested["turn_memory"] = deepcopy(payload)
        updated_result["result"] = nested
    result_session = _d(updated_result.get("session"))
    if result_session:
        result_session["runtime_state"] = _d(updated_session.get("runtime_state"))
        updated_result["session"] = result_session
    return updated_result, updated_session
