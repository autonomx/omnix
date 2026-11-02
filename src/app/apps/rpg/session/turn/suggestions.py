"""What the play screen offers next (RQ-7.3): suggestions from the scene as the turn left it, and, when the game
asks a question, the choices that answer it. Each is a card (evolution roadmap EV-9): a label, the command its log
shows, and the action it carries (the reading the game made of it: family, target, slots), played with no model call.
The Rest, Wait and Status cards are always on offer outside a fight."""
from __future__ import annotations

from typing import Any, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.narration.presentation.outcome_facts import Suggestion
from app.apps.rpg.rules import routines
from app.apps.rpg.rules.contracts import step_ways
from app.apps.rpg.foundation.state import access as _sections

MAX_SUGGESTIONS = 6


def card(label: str, command: str, family: str, target_id: str = "", *, second_target_id: str = "", check: str = "",
         **slots: Any) -> Suggestion:
    """A card: what it shows, the command its log keeps, and the reading it plays."""
    action: dict[str, Any] = {"family": family, **({"target_id": target_id} if target_id else {}),
                              **({"second_target_id": second_target_id} if second_target_id else {}),
                              **({"check": check} if check else {}),
                              **({"slots": {key: value for key, value in slots.items() if value}}
                                 if any(slots.values()) else {})}
    return Suggestion(label=label, command=command, action=action)


def standing_cards(fighting: bool) -> list[Suggestion]:
    """The cards always on offer: rest and wait out of a fight, and how the hero stands (EV-9)."""
    standing = [card("Status", "How do I stand?", "status")]
    return standing if fighting else [card("Rest", "I rest for a while.", "rest", rest="while"),
                                      card("Wait", "I wait a while.", "wait"), *standing]


def _place_ids(simulation: Mapping[str, Any]) -> dict[str, str]:
    return {_s(_d(place).get("name")): str(place_id)
            for place_id, place in _d(_d(_sections.world_model_of(simulation)).get("locations")).items()}


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
    """A fight's moves (EV-2): its foes to strike, a known weakness to use, guarding, breaking away (never from a
    fight with no escape), the companions' common orders and the hero's abilities ready to use."""
    foes = _foes(simulation)
    blooded = any(_s(_d(row).get("kind")) in {"attack", "parting_blow"}
                  for row in _l(_d(_sections.combat_state_of(simulation)).get("combat_log")))
    offered = [card(f"Attack the {_s(foe.get('name'))}", f"I attack the {_s(foe.get('name'))}.", "attack",
                    _s(foe.get("definition_id")) or _s(foe.get("actor_id"))) for foe in foes[:2]]
    known = _known_entries(simulation)
    for foe in foes[:1]:  # its weakness, when the hero has met or heard of its kind
        weak = next((_d(row) for row in _l(foe.get("vulnerabilities")) if _s(_d(row).get("trigger_tag"))), None)
        if weak and _s(foe.get("definition_id")) in known:
            name = (_l(weak.get("aliases")) or [weak.get("trigger_tag")])[0]
            offered.append(card(f"Use its weakness: {name}", f"I use {name} against the {_s(foe.get('name'))}.",
                                "attack", _s(foe.get("definition_id")), weakness=_s(weak.get("trigger_tag"))))
    offered.append(card("Defend", "I defend myself.", "defend"))
    if not any(foe.get("no_escape") for foe in foes):
        offered.append(card("Break away", "I break away and flee.", "flee"))
    for npc_id in routines.companions(simulation)[:1]:
        name = _s(_d(_d(_d(_sections.world_model_of(simulation)).get("npcs")).get(npc_id)).get("name")) or npc_id
        offered += [card(f"{name}: guard me", f"{name}, guard me.", "order", npc_id, order="guard"),
                    card(f"{name}: flank it", f"{name}, flank it.", "order", npc_id, order="flank")]
    if not blooded:  # before blows: slipping past, and for a foe that speaks, talking it down (encounters.md)
        offered.append(card("Slip past", "I sneak past it.", "check", check="sneak"))
        if foes and all(_s(foe.get("kind")) == "person" or foe.get("speaks") is True for foe in foes):
            offered.append(card("Talk it down", "I try to talk it down.", "check", check="persuade"))
    return offered


def _known_entries(simulation: Mapping[str, Any]) -> set[str]:
    from app.apps.rpg.rules.hero_knowledge import known_entries

    return set(known_entries(simulation))


def _ready_abilities(document: Mapping[str, Any]) -> list[Suggestion]:
    """The hero's abilities ready to use in a fight (EV-2), aimed at the first foe standing."""
    from app.apps.rpg.rules import ability_use

    simulation = _d(_sections.simulation_state_of(document))
    foes = _foes(simulation)
    ready = [row for row in ability_use.known(document) if not ability_use.not_ready(document, row)]
    return [card(f"Use {_s(row.get('name'))}", f"I use {_s(row.get('name'))}.", "ability", _s(row.get("ability_id")),
                 second_target_id=_s(foes[0].get("definition_id")) if foes else "")
            for row in ready[:2] if _s(row.get("ability_id"))]


def _level_choice(simulation: Mapping[str, Any]) -> list[Suggestion]:
    """A level's choice waiting (progression.md): raising an attribute, or the two skills the hero has practised
    most, in the words the level rule reads (the playtest: level 2 was reached and nothing said a choice waited)."""
    player = _d(_sections.player_state_of(simulation))
    if int(player.get("level_choices_pending") or 0) <= 0:
        return []
    skills = sorted(_d(player.get("skills")).items(), key=lambda row: (-int(_d(row[1]).get("xp") or 0)
                                                                      - 100 * int(_d(row[1]).get("level") or 0), row[0]))
    offered = [card("Level up: raise strength", "raise strength", "grow", choice="attribute:strength")]
    if len(skills) >= 2:
        first, second = (name.replace("_", " ") for name, _ in skills[:2])
        offered.append(card(f"Level up: improve {first} and {second}", f"improve {first} and {second}", "grow",
                            choice=f"skills:{skills[0][0]},{skills[1][0]}"))
    return offered


def _quest_steps(simulation: Mapping[str, Any], people: list[tuple[str, str]]) -> list[Suggestion]:
    """What the hero's quests ask now (quests.md): a creature their step names, where the quest meets it; the place
    a step names, set out for; someone a step names, when they are here (the playtest: at the Hollow Meridian the
    Archon's fight was not offered, nor Valecourt's road when the princess's engine waited there)."""
    world = _d(_sections.world_model_of(simulation))
    places, here = _d(world.get("locations")), routines.hero_location(simulation)
    creatures = _d(_d(simulation.get("campaign_mechanics")).get("creatures"))
    present = dict(people)
    offered: list[Suggestion] = []
    for quest in map(_d, _l(_d(_sections.quest_state_of(simulation)).get("quests"))):
        steps, stage = [_d(step) for step in _l(quest.get("steps"))], int(_d(quest.get("progress")).get("stage") or 0)
        if quest.get("status") != "active" or stage >= len(steps):
            continue
        quest_places = {_s(place) for place in _l(quest.get("locations"))}
        for condition in (row for way, _ in step_ways(steps[stage]) for row in way):
            if condition.get("defeat") and (here in quest_places or (not quest_places and routines.is_wild(simulation))):
                name = _s(_d(creatures.get(_s(condition["defeat"]))).get("name"))
                if name:
                    offered.append(card(f"Fight the {name}", f"I attack the {name}.", "attack", _s(condition["defeat"])))
            elif condition.get("reach") and _s(condition["reach"]) != here:
                name = _s(_d(places.get(_s(condition["reach"]))).get("name"))
                if name:
                    offered.append(card(f"Go to {name}", f"go to {name}", "move", _s(condition["reach"])))
            elif condition.get("talk") and _s(condition["talk"]) in present:
                name = present[_s(condition["talk"])]
                offered.append(card(f"Talk to {name}", f"Talk to {name}", "talk", _s(condition["talk"])))
    return list({row.command: row for row in offered}.values())[:2]


def suggestions(document: Mapping[str, Any]) -> list[Suggestion]:
    """What to do next where the hero stands: in a fight, its moves; else a level's choice, what the hero's quests ask
    now, the people here, an offered quest, a seller's wares, the roads out, and a look around."""
    simulation = _d(_sections.simulation_state_of(document))
    if _d(_sections.combat_state_of(simulation)).get("active") is True:
        return [*_fight(simulation)[:MAX_SUGGESTIONS], *_ready_abilities(document), *standing_cards(True)]
    people = _people_here(simulation)
    offered = _level_choice(simulation)
    offered += _quest_steps(simulation, people)
    offered += [card(f"Talk to {name}", f"Talk to {name}", "talk", npc_id) for npc_id, name in people[:2]]
    available = [_d(row) for row in _l(_d(_sections.quest_state_of(simulation)).get("quests"))
                 if _s(_d(row).get("status")) == "available" and _s(_d(row).get("title"))]
    # One someone offered first, a finale last (the playtest: the finale was suggested on every screen).
    quest = min(available, key=lambda row: (not row.get("offered_by"), _s(row.get("tier")) == "finale"), default=None)
    if quest:
        title = _s(quest.get("title"))
        offered.append(card(f"Take on {title}", f"I accept the quest {title}.", "quest",
                            _s(quest.get("quest_id") or quest.get("id"))))
    sellers = _d(_d(_sections.world_model_of(simulation)).get("offers"))
    seller = next(((npc_id, name) for npc_id, name in people if _l(sellers.get(npc_id))), None)
    if seller:  # a buy naming no offer: the seller's wares, listed
        offered.append(card(f"See {seller[1]}'s wares", f"I buy supplies from {seller[1]}.", "buy",
                            second_target_id=seller[0]))
    places = _place_ids(simulation)
    offered += [card(f"Go to {place}", f"go to {place}", "move", places.get(place, "")) for place in _exits(simulation)[:2]]
    offered.append(card("Look around", "look around", "look"))
    scene = list({row.command: row for row in offered}.values())[:MAX_SUGGESTIONS]  # each once
    return [*scene, *standing_cards(False)]


def choices(document: Mapping[str, Any], reason: str) -> list[Suggestion]:
    """The answers to the game's question (``reason`` is the reading's: what the command left out)."""
    simulation = _d(_sections.simulation_state_of(document))
    people = _people_here(simulation)
    reason = {"unclear:attack": "attack_without_target", "unclear:move": "move_without_place",
              "unclear:give": "give_without_item"}.get(reason, "unclear" if reason.startswith("unclear") else reason)
    if reason == "attack_without_target":
        foes = [(_s(foe.get("definition_id")), _s(foe.get("name"))) for foe in _foes(simulation)] or people
        return [card(name, f"I attack {name}.", "attack", target) for target, name in foes[:MAX_SUGGESTIONS]]
    if reason == "move_without_place":
        places = _place_ids(simulation)
        return [card(place, f"go to {place}", "move", places.get(place, "")) for place in _exits(simulation)[:MAX_SUGGESTIONS]]
    if reason in {"unclear", "speech_without_listener", "vague_reference", "pronoun_without_antecedent"}:
        return [card(name, f"Talk to {name}", "talk", npc_id) for npc_id, name in people[:MAX_SUGGESTIONS]]
    return []


__all__ = ["MAX_SUGGESTIONS", "Suggestion", "card", "choices", "standing_cards", "suggestions"]
