"""The command grammar applied to a turn: the scene it reads, when the intent model can be skipped,
and what to ask when the command is unclear (RQ-3.1).

The scene is built from the campaign's own state: the people present and the people the world knows,
the creatures of its bestiary, what the player carries, the places and the offers where they stand,
their skills and quests. A confident reading in a family the game resolves without a model skips the
intent call; an unclear command gets a question instead of a guess.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.rules.intent.grammar import IntentCandidate, SceneEntity, SceneView, parse_command
from app.apps.rpg.foundation.state import access as _sections
from app.apps.rpg.foundation.contracts import called as _called

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




# What a thing carried is also called by its kind (the intent gate: "examine my knife" named no Iron Dagger): the last
# word of its name, and that kind's other names. A word of a world's own (a "coilwire monoblade") keeps its own.
_KIND_NAMES = {
    "dagger": ("knife", "blade", "weapon"), "knife": ("dagger", "blade", "weapon"), "sword": ("blade", "weapon"),
    "monoblade": ("blade", "weapon"), "axe": ("weapon",), "bow": ("weapon",), "staff": ("weapon",),
    "pistol": ("gun", "weapon"), "rifle": ("gun", "weapon"), "cloak": ("coat",), "coat": ("cloak",),
    "jacket": ("coat",), "bread": ("food",), "rations": ("food",), "bars": ("food",),
}


def _kind_names(name: str) -> tuple[str, ...]:
    words = name.casefold().split()
    if len(words) < 2:
        return ()
    kind = words[-1]
    return (kind, *_KIND_NAMES.get(kind, ()))


# What an offer is also called by its service (the intent gate: "the price of supper", "buy a room" named no offer
# whose label is "A hot meal" or "A night's lodging").
_SERVICE_NAMES = {
    "lodging": ("a room", "a bed", "lodging", "a room for the night"),
    "meal": ("a meal", "supper", "dinner", "breakfast", "lunch"),
    "drink": ("a drink", "something to drink"),
    "paid_information": ("news", "a rumor", "a rumour", "rumors", "rumours", "information"),
    "repair": ("repairs", "repair work"),
}
# What a place is also called by its kind ("the club" for a nightclub: the intent gate).
_PLACE_KIND_NAMES = {
    "nightclub": ("club",), "club": ("nightclub",), "tavern": ("inn", "pub", "bar"), "inn": ("tavern",),
    "pub": ("tavern", "bar"), "port": ("docks", "harbor", "harbour"), "docks": ("port", "harbor", "harbour"),
    "harbor": ("port", "docks"), "clinic": ("hospital",), "hospital": ("clinic",), "chapel": ("church",),
    "temple": ("shrine",), "market": ("bazaar",), "interchange": ("station",), "station": ("interchange",),
}
_PLACE_KIND_ENDS = re.compile(r"\b(?:built|that|which|where|with|between|beneath|under|above|over|near|by|on|in|at|"
                              r"for|from|of|is|are|was|has|have)\b|[,;:.]")
# A role that leads (the intent gate: "the union leader" for the Red Knives' elected strike coordinator).
_LEADS = frozenset({"leader", "coordinator", "chief", "head", "boss", "director", "commander", "captain",
                    "president", "organizer", "organiser", "chair"})
_GROUP_NOUNS = frozenset({"union", "guild", "collective", "authority", "order", "company", "corporation",
                          "syndicate", "gang", "crew", "cult", "council", "league", "network"})


def _place_kind_names(description: str) -> tuple[str, ...]:
    """A place called by what its description says it is, when it opens by saying so: "A nightclub and neutral
    exchange built around ..." is the nightclub, the club and the exchange. "The mountain winds howl" or "Valecourt,
    in the Heartland" say no kind (the eleventh review: "the mountain" took a look at the mountains for the pass)."""
    opening = re.match(r"\s*(?:a|an)\s+(.*)", description.casefold(), flags=re.DOTALL)
    if opening is None:
        return ()
    head = _PLACE_KIND_ENDS.split(opening.group(1), maxsplit=1)[0].strip()
    words: list[str] = []
    for part in head.split(" and "):
        part_words = part.split()
        # A verb in -s after the noun ends it ("a fortified port moves cargo", "a helix tower combines homes").
        cut = next((index for index, word in enumerate(part_words) if 0 < index < len(part_words) - 1
                    and word.endswith("s") and not word.endswith("ss") and len(word) > 3), len(part_words))
        kept = part_words[:cut]
        if kept and len(kept) <= 4:
            words.append(kept[-1])
    kinds = [kind for word in words for kind in (word, *_PLACE_KIND_NAMES.get(word, ())) if kind.isalpha()]
    return tuple(f"the {kind}" for kind in dict.fromkeys(kinds))


def _leader_names(role: str, groups: Mapping[str, Any]) -> tuple[str, ...]:
    """Someone whose role leads a group the world names, called its leader ("the union leader", "the Red Knives
    leader")."""
    lowered = role.casefold()
    if not set(re.findall(r"[a-z]+", lowered)) & _LEADS:
        return ()
    names: list[str] = []
    for group in groups.values():
        words = [word for word in _s(_d(group).get("name")).split() if word.casefold() != "the"]
        if not words:
            continue
        noun = words[-1].casefold() if words[-1].casefold() in _GROUP_NOUNS else ""
        proper = " ".join(words[:-1] if noun else words)
        # By the group's own name, whole words ("Red Knives" in "elected Red Knives strike coordinator"); a group named
        # only by its noun ("The Order") names no one's leadership (the eleventh review).
        if proper and re.search(rf"\b{re.escape(proper.casefold())}\b", lowered):
            names.append(f"the {proper} leader")
            if noun:
                names.append(f"the {noun} leader")
    return tuple(names)


# What a calling is also called (the intent gate: "ask the trader" named no merchant).
_CALLING_NAMES = {
    "merchant": ("trader", "vendor", "shopkeeper", "seller"), "trader": ("merchant", "vendor"),
    "vendor": ("merchant", "trader", "seller"), "shopkeeper": ("merchant", "shop keeper"),
    "innkeeper": ("barkeep", "bartender", "landlord"), "barkeep": ("bartender", "innkeeper"),
    "bartender": ("barkeep",), "doctor": ("medic", "healer"), "medic": ("doctor", "healer"),
    "healer": ("doctor",), "courier": ("runner", "messenger"), "guard": ("watchman", "guardsman"),
    "captain": ("commander",), "porter": ("carrier",), "smith": ("blacksmith",), "blacksmith": ("smith",),
}


_TITLE_CALLINGS = {"dr": "doctor", "doctor": "doctor", "inspector": "inspector", "captain": "captain",
                   "sergeant": "sergeant", "professor": "professor", "father": "priest", "brother": "brother",
                   "sister": "sister", "mother": "mother", "lord": "lord", "lady": "lady"}


def _title_names(name: str) -> tuple[str, ...]:
    """A title in someone's name names their calling ("Dr. Selene Kade" is the doctor; the intent gate)."""
    first = name.split()[0].casefold().rstrip(".") if name.split() else ""
    calling = _TITLE_CALLINGS.get(first)
    return (f"the {calling}",) if calling and len(name.split()) > 1 else ()


def _role_names(role: str) -> tuple[str, ...]:
    """What someone may be called by what they do: "village guard captain" gives the captain, my captain and the
    guard captain; "guide and first companion" the guide and the companion (the description after "is" aside)."""
    names: list[str] = []
    for part in re.split(r",| and | of | who | for ", role.split(" is ")[0]):
        words = part.split()
        if not words:
            continue
        names += [f"the {words[-1]}", f"my {words[-1]}"]
        names += [f"the {other}" for other in _CALLING_NAMES.get(words[-1], ())]  # "the trader" for a merchant
        if len(words) >= 2:
            names.append(f"the {' '.join(words[-2:])}")
    return tuple(names)


def _label(entity_id: str) -> str:
    return entity_id.rsplit(":", 1)[-1].replace("_", " ").replace("-", " ")


def scene_view(simulation_state: Mapping[str, Any], runtime_state: Mapping[str, Any] | None = None,
               abilities: tuple[tuple[str, str], ...] = ()) -> SceneView:
    """The scene the player stands in, as the command grammar reads it (with whom they are talking to, and the
    hero's abilities, as ``(ability_id, name)``)."""
    state = _d(simulation_state)
    world = _d(_sections.world_model_of(state))
    location_id = _s(_d(_sections.player_state_of(state)).get("location_id") or state.get("location_id"))
    present = set(_l(_d(_sections.present_npc_state_of(state)).get("present_npc_ids")))
    entities: list[SceneEntity] = []
    seen: set[str] = set()

    def add(entity_id: str, kind: str, names: tuple[str, ...], here: bool) -> None:
        if entity_id and names and entity_id not in seen:
            seen.add(entity_id)
            entities.append(SceneEntity(entity_id, kind, names, here=here))  # type: ignore[arg-type]

    people = {**{str(key): _d(value) for key, value in _d(_sections.npc_index_of(state)).items()},
              **{str(key): _d(value) for key, value in _d(world.get("npcs")).items()}}
    for npc_id, npc in people.items():
        name = _s(npc.get("name"))
        role = _s(npc.get("role"))
        add(npc_id, "person", _names(name, _called(name), *(_s(alias) for alias in _l(npc.get("aliases"))),
                                     *_title_names(name),
                                     *_leader_names(role, _d(world.get("groups"))),
                                     f"the {role}" if role and len(role.split()) <= 3 else "",
                                     *_role_names(role.casefold())), npc_id in present)
    for creature_id, creature in _d(_d(state.get("campaign_mechanics")).get("creatures")).items():
        add(str(creature_id), "creature", _names(_d(creature).get("name"), _label(str(creature_id))), True)
    inventory = _d(_sections.inventory_state_of(_d(_sections.player_state_of(state))))
    for item in _l(inventory.get("items")):
        item = _d(item)
        item_id = _s(item.get("item_id") or item.get("id"))
        # By its kind only as the hero's own ("my knife"): never another's ("drop your weapon!": the review).
        add(item_id, "item", _names(item.get("name"), _label(item_id),
                                    *(f"my {kind}" for kind in _kind_names(_s(item.get("name"))))), True)
    for item in _l(_d(_d(state.get("world_items")).get("by_location")).get(location_id)):
        item = _d(item)  # lying where the hero stands, to pick up
        item_id = _s(item.get("item_id") or item.get("id"))
        add(item_id, "item", _names(item.get("name"), _label(item_id)), True)
    for item in _l(world.get("items")):
        item = _d(item)
        add(_s(item.get("id")), "item", _names(item.get("name"), *_kind_names(_s(item.get("name")))), False)
    for group_id, group in _d(world.get("groups")).items():  # the world's factions, unions, networks
        name = _s(_d(group).get("name"))
        add(str(group_id), "group", _names(name, *_kind_names(name)), False)
    here_location = _d(_d(world.get("locations")).get(location_id))
    exits = set(_d(here_location.get("exits")).values())
    for place_id, place in _d(world.get("locations")).items():
        place = _d(place)
        add(str(place_id), "place", _names(place.get("name"), *_l(place.get("aliases")),
                                           *_place_kind_names(_s(place.get("description")))), str(place_id) in exits)
    for provider_id, offers in _d(world.get("offers")).items():
        provider = _d(_d(world.get("providers")).get(provider_id))
        here = _s(provider.get("location_id")) == location_id
        for offer in _l(offers):
            offer = _d(offer)
            # By its service only where it is sold ("any news of Malrec?" in the village is no question about the
            # news Elyra sells at the ruins: the eleventh review).
            service = _SERVICE_NAMES.get(_s(offer.get("service_kind")), ()) if here else ()
            add(_s(offer.get("offer_id")), "offer", _names(offer.get("label"), *service), here)
    for skill_id in _d(_d(_sections.player_state_of(state)).get("skills")):
        add(f"skill:{skill_id}", "skill", _names(str(skill_id).replace("_", " ")), True)
    for quest in _l(_d(_sections.quest_state_of(state)).get("quests")):
        quest = _d(quest)
        add(_s(quest.get("quest_id") or quest.get("id")), "quest", _names(quest.get("title")), True)
    for quest_id, quest in _d(world.get("quests")).items():  # the world's, not offered yet: named, to be refused
        add(_s(quest_id), "quest", _names(_d(quest).get("title")), False)
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
