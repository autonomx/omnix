"""The command grammar applied to a turn: the scene it reads, when the intent model can be skipped,
and what to ask when the command is unclear (RQ-3.1).

The scene is built from the campaign's own state: the people present and the people the world knows,
the creatures of its bestiary, what the player carries, the places and the offers where they stand,
their skills and quests. A confident reading in a family the game resolves without a model skips the
intent call; an unclear command gets a question instead of a guess.
"""
from __future__ import annotations

from typing import Any, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.rules.intent.grammar import IntentCandidate, SceneEntity, SceneView, parse_command

# Families the game resolves with its own rules, so a confident reading needs no intent model call.
# Speech (talk, ask) still goes to the dialogue call, which chooses who answers and writes their line;
# trade goes to the service matcher; raising a hand against a person is left to the model, which reads
# what it means. Travel needs a place and an attack a creature.
RESOLVED_WITHOUT_MODEL = frozenset({"look", "wait", "rest", "status", "flee", "defend", "move", "attack"})
SKIP_CONFIDENCE = 0.8

_CLARIFICATIONS = {
    "give_without_item": "What do you want to give, and to whom?",
    "attack_without_target": "Who or what do you want to attack?",
    "move_without_place": "Where do you want to go?",
    "vague_reference": "Who or what do you mean?",
    "pronoun_without_antecedent": "Who or what do you mean?",
    "speech_without_listener": "Who are you speaking to?",
}


def _names(*values: Any) -> tuple[str, ...]:
    names: list[str] = []
    for value in values:
        text = _s(value).strip()
        if text and text.casefold() not in {name.casefold() for name in names}:
            names.append(text)
    return tuple(names)


def _label(entity_id: str) -> str:
    return entity_id.rsplit(":", 1)[-1].replace("_", " ").replace("-", " ")


def scene_view(simulation_state: Mapping[str, Any], runtime_state: Mapping[str, Any] | None = None,
               abilities: tuple[tuple[str, str], ...] = ()) -> SceneView:
    """The scene the player stands in, as the command grammar reads it (with whom they are talking to, and the
    hero's abilities, as ``(ability_id, name)``)."""
    state = _d(simulation_state)
    world = _d(state.get("world_model"))
    location_id = _s(_d(state.get("player_state")).get("location_id") or state.get("location_id"))
    present = set(_l(_d(state.get("present_npc_state")).get("present_npc_ids")))
    entities: list[SceneEntity] = []
    seen: set[str] = set()

    def add(entity_id: str, kind: str, names: tuple[str, ...], here: bool) -> None:
        if entity_id and names and entity_id not in seen:
            seen.add(entity_id)
            entities.append(SceneEntity(entity_id, kind, names, here=here))  # type: ignore[arg-type]

    people = {**{str(key): _d(value) for key, value in _d(state.get("npc_index")).items()},
              **{str(key): _d(value) for key, value in _d(world.get("npcs")).items()}}
    for npc_id, npc in people.items():
        name = _s(npc.get("name"))
        first = name.split()[0] if name else ""
        role = _s(npc.get("role"))
        add(npc_id, "person", _names(name, first, f"the {role}" if role and len(role.split()) <= 3 else ""),
            npc_id in present)
    for creature_id, creature in _d(_d(state.get("campaign_mechanics")).get("creatures")).items():
        add(str(creature_id), "creature", _names(_d(creature).get("name"), _label(str(creature_id))), True)
    inventory = _d(_d(state.get("player_state")).get("inventory_state"))
    for item in _l(inventory.get("items")):
        item = _d(item)
        item_id = _s(item.get("item_id") or item.get("id"))
        add(item_id, "item", _names(item.get("name"), _label(item_id)), True)
    for item in _l(world.get("items")):
        item = _d(item)
        add(_s(item.get("id")), "item", _names(item.get("name")), False)
    here_location = _d(_d(world.get("locations")).get(location_id))
    exits = set(_d(here_location.get("exits")).values())
    for place_id, place in _d(world.get("locations")).items():
        place = _d(place)
        add(str(place_id), "place", _names(place.get("name"), *_l(place.get("aliases"))), str(place_id) in exits)
    for provider_id, offers in _d(world.get("offers")).items():
        provider = _d(_d(world.get("providers")).get(provider_id))
        for offer in _l(offers):
            offer = _d(offer)
            add(_s(offer.get("offer_id")), "offer", _names(offer.get("label")),
                _s(provider.get("location_id")) == location_id)
    for skill_id in _d(_d(state.get("player_state")).get("skills")):
        add(f"skill:{skill_id}", "skill", _names(str(skill_id).replace("_", " ")), True)
    for quest in _l(_d(state.get("quest_state")).get("quests")):
        quest = _d(quest)
        add(_s(quest.get("quest_id") or quest.get("id")), "quest", _names(quest.get("title")), True)
    focus = _s(_d(_d(runtime_state).get("dialogue_focus")).get("target_id"))
    for ability_id, name in abilities:
        add(ability_id, "ability", (name,), False)
    return SceneView(tuple(entities), focus_id=focus if focus in present else "")


def read_command(
    simulation_state: Mapping[str, Any],
    player_input: str,
    runtime_state: Mapping[str, Any] | None = None,
    abilities: tuple[tuple[str, str], ...] = (),
) -> IntentCandidate:
    return parse_command(player_input, scene_view(simulation_state, runtime_state, abilities))


def skip_reason(reading: IntentCandidate) -> str:
    """Why the intent model is not needed for this reading, or "" when it is."""
    if reading.family in RESOLVED_WITHOUT_MODEL and reading.confidence >= SKIP_CONFIDENCE:
        if reading.family == "move" and reading.target_kind != "place":
            return ""
        if reading.family == "attack" and reading.target_kind != "creature":
            return ""
        return f"grammar:{reading.family}"
    return ""


def clarification(reading: IntentCandidate) -> str:
    """The question to ask when the command is unclear in any situation, or "" when the turn should go on.

    A bare "yes" or "attack" can mean something (accepting a pending offer, striking the foe in a fight), so
    only readings that are unclear whatever is going on are asked about here.
    """
    if reading.family != "clarify" or reading.confidence < SKIP_CONFIDENCE:
        return ""
    return _CLARIFICATIONS.get(reading.reason, "")


def reading_record(reading: IntentCandidate) -> dict[str, Any]:
    """The reading as the turn records it (TurnOutcome.intent and diagnostics)."""
    return {
        "source": "command_grammar_v1",
        "family": reading.family,
        "target_id": reading.target_id,
        "target_kind": reading.target_kind,
        "second_target_id": reading.second_target_id,
        "confidence": reading.confidence,
        "reason": reading.reason,
        "clauses": list(reading.clauses),
    }


__all__ = ["RESOLVED_WITHOUT_MODEL", "clarification", "read_command", "reading_record", "scene_view", "skip_reason"]
