"""What the hero knows of the world (evolution roadmap EV-1): one record, judged after every turn. Pure.

Each entry of the world (a person, a creature, a place, a thing, a group, a quest) the hero has met, visited or
heard of is kept with how (``EntryMet``; a stronger kind replaces a weaker one). After a turn, ``entries_met`` reads
the turn's own changes and the scene the hero ends it in, as quest progress is judged: the place they stand in is
visited, the people present and the companions at their side are met, what they took into their pack is met, a quest
offered or held is met. Hearing of an entry comes from narration, so it is a proposal (EV-11): ``heard_of`` is the
rule that folds it in, or refuses it.

The journal, the game master's panel and the lore links (EV-12) read the record (``known_entries``).
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_str as _s
from app.apps.rpg.foundation.state import access as _sections
from app.apps.rpg.foundation.state.changes import (
    CompanionJoined,
    DialogueExchanged,
    EntryMet,
    KNOWING_RANK,
    ItemAdded,
    ItemPickedUp,
    LocationChanged,
    QuestOffered,
    QuestStatusChanged,
    StateChange,
)
from app.apps.rpg.foundation.state.proposals import Folded, refused

# The world model's collections, and the kind of entry each holds.
_KEYED = (("npcs", "person"), ("locations", "place"), ("groups", "group"), ("quests", "quest"))


def world_entries(simulation: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Every entry of the campaign's world, by id: its row, with its ``family``."""
    world = _d(_sections.world_model_of(simulation))
    entries: dict[str, dict[str, Any]] = {}
    for key, family in _KEYED:
        for entry_id, row in _d(world.get(key)).items():
            entries[str(entry_id)] = {**_d(row), "family": family}
    for row in world.get("items") or ():
        if isinstance(row, Mapping) and _s(row.get("id")):
            entries[_s(row.get("id"))] = {**row, "family": "item"}
    creatures = _d(_d(_sections.campaign_mechanics_of(simulation)).get("creatures"))
    for entry_id, row in creatures.items():
        entries[str(entry_id)] = {**_d(row), "family": "creature"}
    return entries


def known_entries(simulation: Mapping[str, Any]) -> dict[str, str]:
    """What the hero knows, by entry id: "visited", "met" or "heard_of"."""
    entries = _d(_d(_sections.hero_knowledge_of(simulation)).get("entries"))
    return {str(entry_id): _s(_d(row).get("kind")) for entry_id, row in entries.items()}


def _hidden(row: Mapping[str, Any]) -> bool:
    """An entry the world keeps from the hero until it is found: a hidden place, a secret thing (EV-10)."""
    return row.get("hidden") is True or row.get("secret") is True


def _here(simulation: Mapping[str, Any]) -> str:
    player = _d(_sections.player_state_of(simulation))
    return _s(player.get("location_id") or simulation.get("location_id") or simulation.get("current_location_id"))


def _seen(simulation: Mapping[str, Any], applied: Iterable[StateChange]) -> list[tuple[str, str]]:
    """(entry id, kind) for what the turn and the scene it ends in show the hero, in a fixed order."""
    seen: list[tuple[str, str]] = []
    for change in applied:
        if isinstance(change, LocationChanged):
            seen.append((change.location_id, "visited"))
        elif isinstance(change, (ItemAdded, ItemPickedUp)):
            seen.append((change.item_id, "met"))
        elif isinstance(change, (QuestOffered, QuestStatusChanged)):
            seen.append((change.quest_id, "met"))
        elif isinstance(change, (DialogueExchanged, CompanionJoined)):
            seen.append((change.npc_id, "met"))
    if _here(simulation):
        seen.append((_here(simulation), "visited"))
    present = _d(_sections.present_npc_state_of(simulation)).get("present_npc_ids") or ()
    seen += [(_s(npc_id), "met") for npc_id in present if _s(npc_id)]
    party = _d(_sections.party_state_of(_d(_sections.player_state_of(simulation))))
    seen += [(_s(_d(row).get("npc_id")), "met") for row in party.get("companions") or () if _d(row).get("npc_id")]
    return seen


def entries_met(simulation: Mapping[str, Any], applied: Iterable[StateChange]) -> list[EntryMet]:
    """The entries of the world the turn showed the hero that the record does not hold as well yet."""
    entries = world_entries(simulation)
    known = known_entries(simulation)
    met: dict[str, str] = {}
    for entry_id, kind in _seen(simulation, applied):
        if entry_id not in entries:
            continue
        best = max(KNOWING_RANK.get(known.get(entry_id, ""), 0), KNOWING_RANK.get(met.get(entry_id, ""), 0))
        if KNOWING_RANK[kind] > best:
            met[entry_id] = kind
    return [EntryMet(entry_id=entry_id, kind=kind, source="turn") for entry_id, kind in met.items()]  # type: ignore[arg-type]


def heard_of(document: Mapping[str, Any], payload: Mapping[str, Any]) -> Folded:
    """A proposal that the hero heard of an entry (narration named it, EV-12): folded in as ``EntryMet`` when the
    entry is the world's, not kept from the hero, and not known yet."""
    simulation = _d(_sections.simulation_state_of(document))
    entry_id = _s(payload.get("entry_id"))
    row = world_entries(simulation).get(entry_id)
    if row is None:
        return refused(f"no entry {entry_id!r} in this world")
    if _hidden(row):
        return refused("the world keeps this entry from the hero until it is found")
    if entry_id in known_entries(simulation):
        return refused("the hero already knows it")
    return Folded([EntryMet(entry_id=entry_id, kind="heard_of", source=_s(payload.get("source")) or "narration")])


def seeded_record(simulation: Mapping[str, Any]) -> dict[str, Any]:
    """The record an older campaign starts with (document version 12): the places visited, the people present and
    at the hero's side, the people who told the hero something, the quests held and the world's things in the pack."""
    entries = world_entries(simulation)
    location = _d(_sections.travel_state_of(simulation))
    visited = [*(simulation.get("visited_locations") or ()), *(location.get("visited_location_ids") or ())]
    told = _d(_d(simulation.get("dialogue")).get("known_facts"))
    quests = [row for row in _d(_sections.quest_state_of(simulation)).get("quests") or () if isinstance(row, Mapping)]
    pack = _d(_sections.inventory_state_of(_d(_sections.player_state_of(simulation))))
    seen = [(_s(place), "visited") for place in visited]
    seen += [(_s(npc_id), "met") for npc_id in told]
    seen += [(_s(row.get("quest_id") or row.get("id")), "met") for row in quests
             if _s(row.get("status")) in {"active", "completed", "failed"} or row.get("offered_by")]
    seen += [(_s(_d(row).get("item_id")), "met") for row in pack.get("items") or ()]
    tick = int(simulation.get("tick") or 0)
    record: dict[str, dict[str, Any]] = {}
    for entry_id, kind in [*seen, *_seen(simulation, ())]:
        if entry_id in entries and KNOWING_RANK[kind] > KNOWING_RANK.get(_s(_d(record.get(entry_id)).get("kind")), 0):
            record[entry_id] = {"kind": kind, "tick": tick}
    return {"entries": record}


__all__ = ["entries_met", "heard_of", "known_entries", "seeded_record", "world_entries"]
