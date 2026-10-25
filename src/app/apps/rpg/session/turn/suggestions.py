"""What the play screen offers next (RQ-7.3): suggestions from the scene as the turn left it, and, when the game
asks a question, the choices that answer it. Each is a label and the command it sends; the rules decide what the
command does, so a suggestion is only a shortcut for typing it."""
from __future__ import annotations

from typing import Any, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.narration.presentation.outcome_facts import Suggestion
from app.apps.rpg.rules import routines

MAX_SUGGESTIONS = 6


def _people_here(simulation: Mapping[str, Any]) -> list[tuple[str, str]]:
    people = _d(_d(simulation.get("world_model")).get("npcs"))
    party = set(routines.companions(simulation))
    return [(npc_id, _s(_d(people.get(npc_id)).get("name"))) for npc_id in routines.present_now(simulation)[1]
            if npc_id not in party and _s(_d(people.get(npc_id)).get("name"))]


def _exits(simulation: Mapping[str, Any]) -> list[str]:
    world = _d(simulation.get("world_model"))
    here, places = routines.hero_location(simulation), _d(world.get("locations"))
    ends = [(_s(_d(route).get("from")), _s(_d(route).get("to"))) for route in _l(world.get("routes"))]
    neighbours = dict.fromkeys(b if a == here else a for a, b in ends if here in (a, b))
    return [_s(_d(places.get(place)).get("name")) for place in neighbours if _s(_d(places.get(place)).get("name"))]


def _foes(simulation: Mapping[str, Any]) -> list[dict[str, Any]]:
    combat = _d(simulation.get("combat_state"))
    return [_d(row) for row in _d(combat.get("participants")).values()
            if _s(_d(row).get("side")) == "enemy" and _s(_d(row).get("status") or "active") == "active"
            and int(_d(row).get("hp") or 0) > 0]


def _fight(simulation: Mapping[str, Any]) -> list[Suggestion]:
    foes = _foes(simulation)
    blooded = any(_s(_d(row).get("kind")) in {"attack", "parting_blow"}
                  for row in _l(_d(simulation.get("combat_state")).get("combat_log")))
    offered = [Suggestion(label=f"Attack the {_s(foe.get('name'))}", command=f"I attack the {_s(foe.get('name'))}.")
               for foe in foes[:2]]
    offered += [Suggestion(label="Defend", command="I defend myself."),
                Suggestion(label="Break away", command="I break away and flee.")]
    if not blooded:  # before blows: slipping past, and for a foe that speaks, talking it down (encounters.md)
        offered.append(Suggestion(label="Slip past", command="I sneak past it."))
        if foes and all(_s(foe.get("kind")) == "person" or foe.get("speaks") is True for foe in foes):
            offered.append(Suggestion(label="Talk it down", command="I try to talk it down."))
    return offered


def suggestions(document: Mapping[str, Any]) -> list[Suggestion]:
    """What to do next where the hero stands: in a fight, its moves; else the people here, an offered quest, a
    seller's wares, the roads out, and a look around."""
    simulation = _d(document.get("simulation_state"))
    if _d(simulation.get("combat_state")).get("active") is True:
        return _fight(simulation)[:MAX_SUGGESTIONS]
    people = _people_here(simulation)
    offered = [Suggestion(label=f"Talk to {name}", command=f"Talk to {name}") for _, name in people[:2]]
    quest = next((_d(row) for row in _l(_d(simulation.get("quest_state")).get("quests"))
                  if _s(_d(row).get("status")) == "available" and _s(_d(row).get("title"))), None)
    if quest:
        title = _s(quest.get("title"))
        offered.append(Suggestion(label=f"Take on {title}", command=f"I accept the quest {title}."))
    sellers = _d(_d(simulation.get("world_model")).get("offers"))
    seller = next((name for npc_id, name in people if _l(sellers.get(npc_id))), "")
    if seller:
        offered.append(Suggestion(label=f"See {seller}'s wares", command=f"I buy supplies from {seller}."))
    offered += [Suggestion(label=f"Go to {place}", command=f"go to {place}") for place in _exits(simulation)[:2]]
    offered.append(Suggestion(label="Look around", command="look around"))
    return offered[:MAX_SUGGESTIONS]


def choices(document: Mapping[str, Any], reason: str) -> list[Suggestion]:
    """The answers to the game's question (``reason`` is the reading's: what the command left out)."""
    simulation = _d(document.get("simulation_state"))
    people = _people_here(simulation)
    if reason == "attack_without_target":
        foes = [_s(foe.get("name")) for foe in _foes(simulation)] or [name for _, name in people]
        return [Suggestion(label=name, command=f"I attack {name}.") for name in foes[:MAX_SUGGESTIONS]]
    if reason == "move_without_place":
        return [Suggestion(label=place, command=f"go to {place}") for place in _exits(simulation)[:MAX_SUGGESTIONS]]
    if reason in {"speech_without_listener", "vague_reference", "pronoun_without_antecedent"}:
        return [Suggestion(label=name, command=f"Talk to {name}") for _, name in people[:MAX_SUGGESTIONS]]
    return []


__all__ = ["MAX_SUGGESTIONS", "Suggestion", "choices", "suggestions"]
