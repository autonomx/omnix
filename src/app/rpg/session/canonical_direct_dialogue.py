"""Construct non-stateful dialogue intent without accepting legacy visible prose."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list | tuple) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _diagnostics(*advisories: Mapping[str, Any]) -> dict[str, Any]:
    for advisory in advisories:
        value = _mapping(advisory).get("first_call_grounding_diagnostics")
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _speaker(
    action_advisory: Mapping[str, Any],
    semantic_advisory: Mapping[str, Any],
) -> tuple[str, str]:
    diagnostics = _diagnostics(semantic_advisory, action_advisory)
    packet = _mapping(diagnostics.get("turn_grounding_packet"))
    priority = _mapping(packet.get("priority_context"))
    npc_context = _mapping(packet.get("npc_context"))
    addressed_ids = [
        _text(value) for value in _list(priority.get("addressed_npc_ids"))
        if _text(value)
    ]
    profiles = [
        _mapping(value) for value in _list(npc_context.get("addressed_npcs"))
        if isinstance(value, Mapping)
    ]
    selected = profiles[0] if profiles else {}
    raw_id = _text(
        addressed_ids[0] if addressed_ids else ""
    ) or _text(selected.get("id") or selected.get("npc_id")) or _text(
        _mapping(semantic_advisory).get("target_id")
        or _mapping(action_advisory).get("target_id")
    )
    name = _text(selected.get("name")) or _text(
        _mapping(semantic_advisory).get("target_name")
        or _mapping(action_advisory).get("target_name")
    )
    if not raw_id and name:
        raw_id = f"npc:{name.casefold().replace(' ', '_')}"
    if raw_id and not raw_id.startswith("npc:"):
        raw_id = f"npc:{raw_id.casefold().replace(' ', '_')}"
    if not name and raw_id:
        name = raw_id.split(":", 1)[-1].replace("_", " ").title()
    return raw_id or "npc:unknown", name or "NPC"


def build_canonical_direct_dialogue_intent(
    *,
    session: Mapping[str, Any],
    simulation_state: Mapping[str, Any],
    runtime_state: Mapping[str, Any],
    player_input: str,
    action_advisory: Mapping[str, Any],
    semantic_advisory: Mapping[str, Any],
) -> dict[str, Any]:
    """Return target and grounding data only; the Narrative Engine owns all prose."""

    speaker_id, speaker = _speaker(action_advisory, semantic_advisory)
    diagnostics = _diagnostics(semantic_advisory, action_advisory)
    resolved = {
        "ok": True,
        "action_type": "npc_interpretive_dialogue",
        "semantic_action_type": "npc_interpretive_dialogue",
        "semantic_family": "social",
        "response_mode": "dialogue",
        "stateful": False,
        "needs_runtime_resolution": False,
        "target_id": speaker_id,
        "target_name": speaker,
        "outcome": "canonical_narrative_required",
        "first_call_grounding_diagnostics": deepcopy(diagnostics),
        "source": "canonical_direct_dialogue_intent_v1",
    }
    return {
        "consumed": True,
        "ok": True,
        "result": deepcopy(resolved),
        "resolved_result": deepcopy(resolved),
        "npc": {
            "speaker": speaker,
            "speaker_id": speaker_id,
        },
        "visible_response": {},
        "narration": "",
        "final_narration": "",
        "summary": "",
        "first_call_action_advisory": deepcopy(dict(action_advisory)),
        "first_call_semantic_advisory": deepcopy(dict(semantic_advisory)),
        "first_call_grounding_diagnostics": deepcopy(diagnostics),
        "stateful": False,
        "needs_runtime_resolution": False,
        "simulation_state": deepcopy(dict(simulation_state)),
        "runtime_state": deepcopy(dict(runtime_state)),
        "session": deepcopy(dict(session)),
        "player_input": _text(player_input),
        "source": "canonical_direct_dialogue_intent_v1",
        "legacy_visible_prose_consumed": False,
    }
