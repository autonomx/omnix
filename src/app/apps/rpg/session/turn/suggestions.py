"""What the play screen offers next (RQ-7.3): suggestions from the scene as the turn left it, and, when the game
asks a question, the choices that answer it. Each is a label and the command it sends; the rules decide what the
command does, so a suggestion is only a shortcut for typing it."""
from __future__ import annotations

from typing import Any, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.narration.presentation.outcome_facts import Suggestion
from app.apps.rpg.rules import routines
from app.apps.rpg.foundation.state import access as _sections

MAX_SUGGESTIONS = 6


def _people_here(simulation: Mapping[str, Any]) -> list[tuple[str, str]]:
    people = _d(_d(_sections.world_model_of(simulation)).get("npcs"))
    party = set(routines.companions(simulation))
    return [(npc_id, _s(_d(people.get(npc_id)).get("name"))) for npc_id in routines.present_now(simulation)[1]
            if npc_id not in party and _s(_d(people.get(npc_id)).get("name"))]


def _exits(simulation: Mapping[str, Any]) -> list[str]:
    world = _d(_sections.world_model_of(simulation))
    here, places = routines.hero_location(simulation), _d(world.get("locations"))
    ends = [(_s(_d(route).get("from")), _s(_d(route).get("to"))) for route in _l(world.get("routes"))]
    neighbours = dict.fromkeys(b if a == here else a for a, b in ends if here in (a, b))
    return [_s(_d(places.get(place)).get("name")) for place in neighbours if _s(_d(places.get(place)).get("name"))]


def _foes(simulation: Mapping[str, Any]) -> list[dict[str, Any]]:
    combat = _d(_sections.combat_state_of(simulation))
    return [_d(row) for row in _d(combat.get("participants")).values()
            if _s(_d(row).get("side")) == "enemy" and _s(_d(row).get("status") or "active") == "active"
            and int(_d(row).get("hp") or 0) > 0]


def _fight(simulation: Mapping[str, Any]) -> list[Suggestion]:
    foes = _foes(simulation)
    blooded = any(_s(_d(row).get("kind")) in {"attack", "parting_blow"}
                  for row in _l(_d(_sections.combat_state_of(simulation)).get("combat_log")))
    offered = [Suggestion(label=f"Attack the {_s(foe.get('name'))}", command=f"I attack the {_s(foe.get('name'))}.")
               for foe in foes[:2]]
    offered += [Suggestion(label="Defend", command="I defend myself."),
                Suggestion(label="Break away", command="I break away and flee.")]
    if not blooded:  # before blows: slipping past, and for a foe that speaks, talking it down (encounters.md)
        offered.append(Suggestion(label="Slip past", command="I sneak past it."))
        if foes and all(_s(foe.get("kind")) == "person" or foe.get("speaks") is True for foe in foes):
            offered.append(Suggestion(label="Talk it down", command="I try to talk it down."))
    return offered


def _level_choice(simulation: Mapping[str, Any]) -> list[Suggestion]:
    """A level's choice waiting (progression.md): raising an attribute, or the two skills the hero has practised
    most, in the words the level rule reads (the playtest: level 2 was reached and nothing said a choice waited)."""
    player = _d(_sections.player_state_of(simulation))
    if int(player.get("level_choices_pending") or 0) <= 0:
        return []
    skills = sorted(_d(player.get("skills")).items(), key=lambda row: (-int(_d(row[1]).get("xp") or 0)
                                                                      - 100 * int(_d(row[1]).get("level") or 0), row[0]))
    offered = [Suggestion(label="Level up: raise strength", command="raise strength")]
    if len(skills) >= 2:
        first, second = (name.replace("_", " ") for name, _ in skills[:2])
        offered.append(Suggestion(label=f"Level up: improve {first} and {second}",
                                  command=f"improve {first} and {second}"))
    return offered


def suggestions(document: Mapping[str, Any]) -> list[Suggestion]:
    """What to do next where the hero stands: in a fight, its moves; else the people here, an offered quest, a
    seller's wares, the roads out, and a look around."""
    simulation = _d(_sections.simulation_state_of(document))
    if _d(_sections.combat_state_of(simulation)).get("active") is True:
        return _fight(simulation)[:MAX_SUGGESTIONS]
    people = _people_here(simulation)
    offered = _level_choice(simulation)
    offered += [Suggestion(label=f"Talk to {name}", command=f"Talk to {name}") for _, name in people[:2]]
    available = [_d(row) for row in _l(_d(_sections.quest_state_of(simulation)).get("quests"))
                 if _s(_d(row).get("status")) == "available" and _s(_d(row).get("title"))]
    # One someone offered first, a finale last (the playtest: the finale was suggested on every screen).
    quest = min(available, key=lambda row: (not row.get("offered_by"), _s(row.get("tier")) == "finale"), default=None)
    if quest:
        title = _s(quest.get("title"))
        offered.append(Suggestion(label=f"Take on {title}", command=f"I accept the quest {title}."))
    sellers = _d(_d(_sections.world_model_of(simulation)).get("offers"))
    seller = next((name for npc_id, name in people if _l(sellers.get(npc_id))), "")
    if seller:
        offered.append(Suggestion(label=f"See {seller}'s wares", command=f"I buy supplies from {seller}."))
    offered += [Suggestion(label=f"Go to {place}", command=f"go to {place}") for place in _exits(simulation)[:2]]
    offered.append(Suggestion(label="Look around", command="look around"))
    return offered[:MAX_SUGGESTIONS]


def choices(document: Mapping[str, Any], reason: str) -> list[Suggestion]:
    """The answers to the game's question (``reason`` is the reading's: what the command left out)."""
    simulation = _d(_sections.simulation_state_of(document))
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
