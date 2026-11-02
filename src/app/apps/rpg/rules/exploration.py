"""Exploring: what is hidden is found, and a site's rooms are met (evolution roadmap EV-10). Pure.

What anyone would see of an area shows on arrival; what is hidden (a cave in the hills, a cellar under the inn) is
found by exploring (``explore``): a seeded search, the hero's roll against the place's difficulty, for each hidden
place whose road leads here. Found, it joins the roads (``SiteFound``). Exploring makes no generation call: where
nothing has been filled in yet, the search finds nothing this time.

A site has a fixed shape (``build_site``): the game master names it and its rooms and writes their descriptions; code
lays the rooms out, one way leading to the next, gives each an encounter from the world's creatures sized to the
hero's level, the last its boss, and its reward among the world's things. Arriving in a room whose encounter stands,
the hero meets it (``room_foe``); beaten, or its loot taken, the room is cleared (``rooms_cleared``, ``RoomCleared``).
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state import access as _sections
from app.apps.rpg.foundation.state.changes import (
    CombatAdvanced,
    CombatEnded,
    ItemPickedUp,
    RoomCleared,
    SiteFound,
    StateChange,
)

DEFAULT_DIFFICULTY = 12
HAZARD_SHARE = 0.4  # the rooms of a site (not its last) that hold a hazard, met by a check on arriving
_HAZARDS = (("climb", "A crumbling ledge must be climbed.", "You climb the ledge.", "You slip on the ledge"),
            ("notice", "A tripwire is strung across the way.", "You spot the tripwire and step over it.",
             "A tripwire snaps a dart into you"),
            ("climb", "The floor gives way to a pit.", "You leap the pit.", "You fall into the pit"))
SEARCH_MINUTES = 30
_ROOM_NAMES = ("the entrance", "the first chamber", "the narrow passage", "the deep hall", "the innermost chamber")


@dataclass(frozen=True)
class Explored:
    changes: list[StateChange] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    minutes: int = SEARCH_MINUTES


def _here(simulation: Mapping[str, Any]) -> str:
    from app.apps.rpg.rules.routines import hero_location

    return hero_location(simulation)


def hidden_here(simulation: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The hidden places whose road leads where the hero stands: (their id, name, difficulty), hardest last."""
    here = _here(simulation)
    locations = _d(_d(_sections.world_model_of(simulation)).get("locations"))
    found = []
    for entry_id, row in _d(_d(_sections.lore_layer_of(simulation)).get("entries")).items():
        place = _d(locations.get(entry_id))
        roads = _l(_d(_d(row).get("play")).get("roads"))
        if place.get("hidden") is True and any(_s(_d(road).get("to")) == here for road in roads):
            found.append({"id": str(entry_id), "name": _s(place.get("name")),
                          "difficulty": int(place.get("difficulty") or DEFAULT_DIFFICULTY)})
    return sorted(found, key=lambda row: (row["difficulty"], row["id"]))


def _bonus(simulation: Mapping[str, Any]) -> int:
    skills = _d(_d(_sections.player_state_of(simulation)).get("skills"))
    return max(int(_d(skills.get(name)).get("level") or 0) for name in ("perception", "survival", "investigation")) \
        if skills else 0


def explore(document: Mapping[str, Any]) -> Explored:
    """The hero searches where they stand: each hidden place whose road leads here is found by a roll of d20 and the
    hero's best searching skill against its difficulty, seeded by the campaign, the turn and the place."""
    from app.apps.rpg.foundation.core.determinism import rng_for, stable_sub_index

    simulation = _d(_sections.simulation_state_of(document))
    hidden = hidden_here(simulation)
    if not hidden:
        return Explored(lines=["You search the area but find nothing this time."])
    seed = int(_sections.rng_seed_of(simulation) or 0) % 2**64
    turn = int(_d(document.get("state")).get("turn_count") or 0)
    changes: list[StateChange] = []
    lines: list[str] = []
    for place in hidden:
        roll = rng_for(seed, turn, "explore", stable_sub_index(place["id"])).randint(1, 20) + _bonus(simulation)
        if roll >= place["difficulty"]:
            told = f"You find {place['name']}."
            changes.append(SiteFound(location_id=place["id"], told=told))
            lines.append(told)
    return Explored(changes=changes, lines=lines or ["You search the area but find nothing this time."])


def build_site(simulation: Mapping[str, Any], site_id: str, rooms: Iterable[Mapping[str, Any]], *,
               boss_id: str = "", reward_item_id: str = "") -> list[dict[str, Any]]:
    """A site's rooms, as code lays them out: the game master's names and descriptions (as many as the budget holds,
    else the plain names), each room the way to the next, an encounter in each from the world's creatures sized to
    the hero's level (seeded by the site), the last its boss's (``boss_id``, when it fits) with its reward."""
    from app.apps.rpg.foundation.core.determinism import rng_for, stable_sub_index
    from app.apps.rpg.rules.budgets import SITE_ROOMS, encounter_fits

    level = max(1, int(_d(_sections.player_state_of(simulation)).get("level") or 1))
    creatures = _d(_d(_sections.campaign_mechanics_of(simulation)).get("creatures"))
    fitting = sorted(creature_id for creature_id, row in creatures.items()
                     if not _d(row).get("boss") and encounter_fits(simulation, [_d(row)], level))
    written = [_d(room) for room in rooms][:SITE_ROOMS.high]
    seed = int(_sections.rng_seed_of(simulation) or 0) % 2**64
    rng = rng_for(seed, 0, "site_layout", stable_sub_index(site_id))
    count = max(SITE_ROOMS.low, min(SITE_ROOMS.high, len(written) or rng.randint(SITE_ROOMS.low, SITE_ROOMS.high)))
    built: list[dict[str, Any]] = []
    for index in range(count):
        room = written[index] if index < len(written) else {}
        last = index == count - 1
        creature = boss_id if last and boss_id in creatures else (rng.choice(fitting) if fitting else "")
        room_id = f"{site_id}:room-{index + 1}"
        hazard = rng.choice(_HAZARDS) if not last and rng.random() < HAZARD_SHARE else None
        built.append({"id": room_id, "name": _s(room.get("name"))[:120] or _ROOM_NAMES[index],
                      "description": _s(room.get("description"))[:600], "from": built[-1]["id"] if built else site_id,
                      "creature_id": creature, **({"loot_item_id": reward_item_id} if last and reward_item_id else {}),
                      **({"hazard": {"check": hazard[0], "difficulty": 10 + level, "told": hazard[1], "passed": hazard[2],
                                     "failed": hazard[3], "damage": 2 + level}} if hazard else {}),
                      "map": room_grid(room_id, rng)})
    return built


def room_grid(room_id: str, rng: Any) -> dict[str, Any]:
    """A room's square grid, laid out by code (EV-10) from the site's seeded stream ``rng``: walls around a floor of a
    size, a pillar or two, the way in at the bottom and the way on at the top. Kept in the room's play data, so a
    campaign replays it."""
    width, height = rng.choice((7, 9)), rng.choice((7, 9))
    rows = [["#" if x in (0, width - 1) or y in (0, height - 1) else "." for x in range(width)] for y in range(height)]
    middle = width // 2
    rows[0][middle] = rows[height - 1][middle] = "."
    for _ in range(rng.randint(0, 2)):
        x, y = rng.randint(2, width - 3), rng.randint(2, height - 3)
        if x != middle:
            rows[y][x] = "#"
    return {"map_id": f"map:{room_id}", "width": width, "height": height, "rows": ["".join(row) for row in rows],
            "arrival": [middle, height - 2]}


def _room(simulation: Mapping[str, Any], location_id: str) -> tuple[str, dict[str, Any]]:
    place = _d(_d(_d(_sections.world_model_of(simulation)).get("locations")).get(location_id))
    site_id = _s(place.get("site_id"))
    if not site_id:
        return "", {}
    site = _d(_d(_d(_sections.lore_layer_of(simulation)).get("entries")).get(site_id))
    room = next((_d(row) for row in _l(_d(_d(site.get("play")).get("site")).get("rooms"))
                 if _s(_d(row).get("id")) == location_id), {})
    return site_id, room


def _cleared(simulation: Mapping[str, Any], site_id: str, room_id: str) -> str:
    return _s(_d(_d(_d(_sections.exploration_of(simulation)).get("cleared")).get(site_id)).get(room_id))


def room_hazard(simulation: Mapping[str, Any], *, turn_key: str) -> tuple[list[StateChange], list[str]]:
    """The hazard of the room the hero arrives in, met once: a roll of d20 and the hero's best searching skill against
    its difficulty, seeded by the campaign, the turn and the room; failed, it hurts."""
    from app.apps.rpg.foundation.core.determinism import rng_for, stable_sub_index
    from app.apps.rpg.foundation.state.changes import HpChanged

    site_id, room = _room(simulation, _here(simulation))
    hazard = _d(room.get("hazard"))
    room_id = _s(room.get("id"))
    if not hazard or _cleared(simulation, site_id, f"{room_id}:hazard"):
        return [], []
    seed = int(_sections.rng_seed_of(simulation) or 0) % 2**64
    roll = rng_for(seed, 0, f"room_hazard:{turn_key}", stable_sub_index(room_id)).randint(1, 20) + _bonus(simulation)
    met: list[StateChange] = [RoomCleared(site_id=site_id, room_id=f"{room_id}:hazard", how="passed")]
    if roll >= int(hazard.get("difficulty") or DEFAULT_DIFFICULTY):
        return met, [_s(hazard.get("told")), _s(hazard.get("passed"))]
    # A hazard hurts, but never brings the hero down: the fight that may follow is theirs to have.
    player = _d(_sections.player_state_of(simulation))
    hp = int(player.get("hp") or _d(_d(player.get("resources")).get("hp")).get("current") or 0)
    damage = int(hazard.get("damage") or 3)
    damage = max(0, min(damage, hp - 1)) if hp > 0 else damage
    return [*met, *([HpChanged(delta=-damage)] if damage else [])], [
        _s(hazard.get("told")), f"{_s(hazard.get('failed'))} ({damage} damage)."]


def room_waits(simulation: Mapping[str, Any]) -> bool:
    """Whether the room the hero is in holds what must be met before going on: its encounter, or its hazard."""
    site_id, room = _room(simulation, _here(simulation))
    if not room:
        return False
    hazard = bool(room.get("hazard")) and not _cleared(simulation, site_id, f"{_s(room.get('id'))}:hazard")
    return hazard or bool(room_foe(simulation))


def room_foe(simulation: Mapping[str, Any]) -> str:
    """The creature that stands in the room the hero is in, while it is not beaten ("" when none)."""
    site_id, room = _room(simulation, _here(simulation))
    if not room or _cleared(simulation, site_id, _s(room.get("id"))) == "beaten":
        return ""
    return _s(room.get("creature_id"))


def _won(change: StateChange) -> bool:
    """A fight won: the fight rule's last blow (its state ended with the foes' side defeated or fled), or its end."""
    if isinstance(change, CombatAdvanced):
        return change.combat_state.get("active") is False and change.combat_state.get("ended_reason") in {
            "enemy_side_defeated", "enemy_fled"}  # beaten, or put to flight: the encounter no longer stands
    return isinstance(change, CombatEnded) and change.outcome == "victory"


def rooms_cleared(simulation: Mapping[str, Any], applied: Iterable[StateChange]) -> list[StateChange]:
    """The rooms the turn cleared: a fight won where its encounter stood, or its loot taken."""
    site_id, room = _room(simulation, _here(simulation))
    if not room:
        return []
    room_id = _s(room.get("id"))
    applied = list(applied)
    cleared: list[StateChange] = []
    if _cleared(simulation, site_id, room_id) != "beaten" and any(_won(change) for change in applied):
        cleared.append(RoomCleared(site_id=site_id, room_id=room_id, how="beaten"))
    loot = _s(room.get("loot_item_id"))
    if loot and not _cleared(simulation, site_id, room_id) and not cleared and any(
            isinstance(change, ItemPickedUp) and change.item_id == loot for change in applied):
        cleared.append(RoomCleared(site_id=site_id, room_id=room_id, how="looted"))
    return cleared


def site_maps(simulation: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The grids of the sites' rooms in the campaign's lore layer (each ``room_grid``), with the room each is for."""
    return [{**_d(room.get("map")), "location_id": _s(room.get("id"))}
            for row in _d(_d(_sections.lore_layer_of(simulation)).get("entries")).values()
            for room in map(_d, _l(_d(_d(_d(row).get("play")).get("site")).get("rooms"))) if _d(room.get("map"))]


__all__ = ["DEFAULT_DIFFICULTY", "Explored", "build_site", "explore", "hidden_here", "room_foe", "room_grid", "room_waits",
           "room_hazard", "rooms_cleared", "site_maps"]
