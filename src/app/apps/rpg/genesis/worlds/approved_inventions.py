"""Inventions a world's author approved from its campaigns' review (evolution roadmap EV-0, part 2), as its next
publication writes them in: each a lore entity of its kind under its canon id, with its play data in the play
sections (``session/lore_review.py`` keeps the queue and the decisions)."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s

APPROVED_KEY = "lore_review_approved"  # the world's metadata entry: approved inventions, by canon id


def approved_inventions(world: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """The inventions the world's author approved, by canon id: what its next publication writes in."""
    return {str(key): _d(row) for key, row in _d(_d(world.get("metadata")).get(APPROVED_KEY)).items()}


def _rewritten(value: Any, ids: Mapping[str, str]) -> Any:
    """``value`` with each campaign id an approved entry had replaced by its canon id."""
    if isinstance(value, str):
        return ids.get(value, value)
    if isinstance(value, Mapping):
        return {key: _rewritten(item, ids) for key, item in value.items()}
    if isinstance(value, list):
        return [_rewritten(item, ids) for item in value]
    return value


def with_approved_inventions(canon: Mapping[str, Any], topology: Mapping[str, Any],
                             approved: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """``canon`` and ``topology`` with the approved inventions added: each a lore entity of its kind under its canon
    id, and its play data in the play sections (a person's routine and knowledge, an item's gear and offer, a
    creature's numbers, a quest's steps, a place's roads). Only adding."""
    canon, topology = dict(canon), dict(topology)
    ids = {_s(row.get("entry_id")): key for key, row in approved.items() if _s(row.get("entry_id"))}
    entities = [dict(row) for row in _l(canon.get("entities"))]
    known = {_s(_d(row).get("id")) for row in entities}
    kinds = {"person": "character", "place": "location", "item": "item", "creature": "creature", "quest": "quest"}
    sections = {"person": "characters", "item": "items", "creature": "bestiary", "quest": "quests"}
    for key, approved_row in approved.items():
        if key in known:
            continue
        family = _s(approved_row.get("family"))
        row, play = _d(_rewritten(approved_row.get("row"), ids)), _d(_rewritten(approved_row.get("play"), ids))
        entity = {**{name: value for name, value in row.items() if isinstance(value, (str, int, float, bool))},
                  "id": key, "kind": kinds.get(family, family), "name": _s(approved_row.get("name"))}
        entities.append(entity)
        if family == "person":
            if play.get("schedule"):
                canon["routines"] = [*_l(canon.get("routines")), {"npc_id": key, "schedule": play["schedule"]}]
            if play.get("knowledge"):
                canon["knowledge"] = [*_l(canon.get("knowledge")), {"npc_id": key, "facts": play["knowledge"]}]
        elif family == "place":
            topology["locations"] = [*_l(topology.get("locations")), {"id": key, "name": entity["name"],
                                                                      "region_id": _s(row.get("region_id"))}]
            topology["routes"] = [*_l(topology.get("routes")),
                                  *({"id": f"route:{key}:{_s(road.get('to'))}", "from": key, "to": _s(road.get("to")),
                                     "travel_time": _s(road.get("travel_time"))} for road in map(_d, _l(play.get("roads"))))]
        elif family == "item" and isinstance(row.get("equipment"), Mapping):
            entity["equipment"] = _d(row["equipment"])
        elif family == "creature":
            combat = _d(play.get("combat"))
            entity.update({name: combat[name] for name in ("level", "hp", "damage_min", "damage_max", "defense",
                                                           "behaviour") if name in combat})
        elif family == "quest":
            entity.update({"giver_id": _s(row.get("giver_id")), "objective": _s(row.get("objective")),
                           "steps": _l(row.get("steps")), "reward": _d(row.get("reward"))})
        section = sections.get(family)
        if section and _l(canon.get(section)):  # a section the world authored lists it there too (``lore_rows``)
            canon[section] = [*_l(canon.get(section)), {**entity}]
    canon["entities"] = entities
    return canon, topology


def manifest_with_approved(manifest: Mapping[str, Any], approved: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """The revision's entity manifest with each approved entry's canon id in its family's list."""
    lists = {"person": "characters", "place": "locations", "item": "items", "creature": "bestiary", "quest": "quests"}
    manifest = {key: list(value) if isinstance(value, list) else value for key, value in dict(manifest).items()}
    for key, row in approved.items():
        name = lists.get(_s(row.get("family")))
        if name and key not in _l(manifest.get(name)):
            manifest[name] = [*_l(manifest.get(name)), key]
    return manifest


__all__ = ["APPROVED_KEY", "approved_inventions", "manifest_with_approved", "with_approved_inventions"]
