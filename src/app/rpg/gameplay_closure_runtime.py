"""Deterministic gameplay closure helpers for RPG Phase 27."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.rpg.quest_runtime import build_quest_runtime_report
from app.rpg.social_runtime import build_social_runtime_report
from app.rpg.world_runtime import build_world_runtime_report

GAMEPLAY_CLOSURE_RUNTIME_SOURCE = "phase27_gameplay_closure_runtime_v1"


def build_gameplay_closure_report(turn_result: Mapping[str, object]) -> dict[str, object]:
    """Build deterministic closure notes and next-action guidance for one turn."""

    world = build_world_runtime_report(turn_result)
    quest = build_quest_runtime_report(turn_result)
    social = build_social_runtime_report(turn_result)
    suggestions = tuple(_suggestions(world, quest, social))
    effects = {
        "travel": _travel_note(world),
        "quest_deadlines": list(_sequence(quest.get("expired_quest_ids"))),
        "memory_hooks": list(_sequence(social.get("memory_hooks"))),
        "npc_memory_summaries": dict(_mapping(social.get("npc_memory_summaries"))),
    }
    issues = [] if suggestions else ["missing_suggested_next_actions"]
    return {
        "source": GAMEPLAY_CLOSURE_RUNTIME_SOURCE,
        "ready": not issues,
        "issues": issues,
        "effects": effects,
        "suggested_next_actions": list(suggestions),
    }


def _travel_note(world: Mapping[str, object]) -> dict[str, object]:
    travel = _mapping(world.get("travel"))
    if travel.get("ok") is True:
        return {"status": "ready", "target_location_id": world.get("target_location_id")}
    reason = str(travel.get("reason") or "missing_travel")
    return {"status": "blocked", "reason": reason, "requires_expansion": reason == "target_requires_expansion"}


def _suggestions(world: Mapping[str, object], quest: Mapping[str, object], social: Mapping[str, object]) -> tuple[str, ...]:
    suggestions: list[str] = []
    journal = _mapping(quest.get("journal"))
    suggestions.extend(str(item) for item in _sequence(journal.get("suggested_actions")))
    map_debug = _mapping(world.get("map_debug"))
    for exit_id in _sequence(map_debug.get("known_exits")):
        suggestions.append(f"Travel to {exit_id}")
    scene = _mapping(social.get("social_scene"))
    participants = _sequence(scene.get("participants"))
    if participants:
        suggestions.append(f"Ask {participants[0]} what they know")
    travel = _mapping(world.get("travel"))
    if travel.get("reason") == "target_requires_expansion":
        suggestions.append("Scout or describe the new location before travel")
    return tuple(dict.fromkeys(suggestions))[:5]


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(value)
    return ()
