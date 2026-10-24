"""The reducer: the one place campaign state changes (RQ-1.2, roadmap §4.1).

``reduce(document, changes)`` applies a turn's changes to a copy of the document and returns it with the JSON
Patch (RFC 6902) of exactly what it wrote. The patch is built from the writes, not by diffing documents, and
``apply_state_delta(document, patch)`` gives the same document (the property test checks it). The reducer
writes the paths the sections own (``sections.SECTION_PATHS``), in today's (v6) layout: the simulation's
stores, and the play screen's projections of them (the sheet's purse and pack, ``state.quests``) until RQ-2
retires the projections.

The reducer decides nothing: a change the document cannot take (removing an item the pack does not hold, a
quest it does not know) raises ``ChangeRejected``; resolvers check before they propose.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .changes import (
    CombatantHpChanged,
    CombatStarted,
    CombatEnded,
    CompanionJoined,
    CompanionLeft,
    ExperienceGained,
    HpChanged,
    ItemAdded,
    ItemDropped,
    ItemEquipped,
    ItemPickedUp,
    ItemRemoved,
    ItemUnequipped,
    LocationChanged,
    NeedsChanged,
    PresenceChanged,
    PurseChanged,
    QuestPlaceReached,
    QuestStatusChanged,
    SkillProgressed,
    StateChange,
    JournalWritten,
    ServiceReserved,
    StockTaken,
    TimeAdvanced,
    TradeRemembered,
    TurnCounted,
    WorldTicked,
)

JsonPatch = list[dict[str, Any]]
TRADE_LEDGER_KEPT = 50
_PLAYER = ("simulation_state", "player_state")
_STORE = _PLAYER + ("inventory_state",)


class ChangeRejected(ValueError):
    """A change the document cannot take."""


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


class _Writer:
    """Reads and writes paths of a document copy, and remembers the outermost path of each write."""

    def __init__(self, document: dict[str, Any]) -> None:
        self.document = document
        self.written: list[tuple[str, ...]] = []

    def get(self, path: tuple[str, ...], default: Any = None) -> Any:
        value: Any = self.document
        for key in path:
            if not isinstance(value, dict) or key not in value:
                return default
            value = value[key]
        return value

    def set(self, path: tuple[str, ...], value: Any) -> None:
        holder = self.document
        for depth, key in enumerate(path[:-1]):
            child = holder.get(key)
            if not isinstance(child, dict):
                # A missing (or non-object) parent is created whole: the write is of the parent.
                built: Any = value
                for inner in reversed(path[depth + 1:]):
                    built = {inner: built}
                holder[key] = built
                self.written.append(path[: depth + 1])
                return
            holder = child
        holder[path[-1]] = value
        self.written.append(path)

    def patch(self) -> JsonPatch:
        """One ``add`` per outermost written path, in first-write order, with its final value."""
        outermost: list[tuple[str, ...]] = []
        for path in self.written:
            if path in outermost or any(path[: len(other)] == other for other in outermost):
                continue
            outermost = [other for other in outermost if other[: len(path)] != path]
            outermost.append(path)
        return [{"op": "add", "path": "".join(f"/{_escape(key)}" for key in path), "value": deepcopy(self.get(path))}
                for path in outermost]


def _copper(purse: Any) -> int:
    purse = purse if isinstance(purse, dict) else {}
    return int(purse.get("gold") or 0) * 100 + int(purse.get("silver") or 0) * 10 + int(purse.get("copper") or 0)


def _purse(copper: int) -> dict[str, int]:
    return {"gold": copper // 100, "silver": copper // 10 % 10, "copper": copper % 10}


def _items(writer: _Writer) -> list[dict[str, Any]]:
    items = writer.get(_STORE + ("items",))
    return [dict(item) for item in items] if isinstance(items, list) else []


def _key(item: dict[str, Any]) -> str:
    return str(item.get("item_id") or item.get("id") or item.get("name") or "")


def _quantity(item: dict[str, Any]) -> int:
    return int(item.get("qty", item.get("quantity", 1)) or 0)


def _write_items(writer: _Writer, items: list[dict[str, Any]]) -> None:
    writer.set(_STORE + ("items",), items)
    # The play screen's projection of the store (until RQ-2.4 retires it).
    sheet = writer.get(("state", "player", "inventory"))
    previous = {_key(item): item for item in sheet or () if isinstance(item, dict)}
    projected = []
    for item in items:
        public = {**previous.get(_key(item), {}), **{k: v for k, v in item.items() if k != "qty"}}
        public.setdefault("id", _key(item))
        public["quantity"] = _quantity(item)
        projected.append(public)
    writer.set(("state", "player", "inventory"), projected)


def _counted(item: dict[str, Any], quantity: int) -> dict[str, Any]:
    """The stack with ``quantity``: in ``qty``, and in ``quantity`` too where the stack also keeps the sheet's count."""
    return {**item, "qty": quantity, **({"quantity": quantity} if "quantity" in item else {})}


def _take(items: list[dict[str, Any]], item_id: str, quantity: int) -> dict[str, Any]:
    for index, item in enumerate(items):
        if _key(item) == item_id:
            held = _quantity(item)
            if held < quantity:
                raise ChangeRejected(f"the pack holds {held} of {item_id}, not {quantity}")
            taken = _counted(item, quantity)
            if held == quantity:
                items.pop(index)
            else:
                items[index] = _counted(item, held - quantity)
            return taken
    raise ChangeRejected(f"the pack holds no {item_id}")


def _put(items: list[dict[str, Any]], stack: dict[str, Any]) -> None:
    for index, item in enumerate(items):
        if _key(item) == _key(stack):
            items[index] = _counted(item, _quantity(item) + _quantity(stack))
            return
    items.append(stack)


def _ground(writer: _Writer, location_id: str) -> list[dict[str, Any]]:
    stacks = writer.get(("simulation_state", "world_items", "by_location", location_id))
    return [dict(item) for item in stacks] if isinstance(stacks, list) else []


def _quest_rows(writer: _Writer, quest_id: str) -> tuple[list[dict[str, Any]], int]:
    quests = writer.get(("simulation_state", "quest_state", "quests"))
    rows = [dict(row) for row in quests] if isinstance(quests, list) else []
    for index, row in enumerate(rows):
        if quest_id in (row.get("quest_id"), row.get("id")):
            return rows, index
    raise ChangeRejected(f"no quest {quest_id}")


def _write_quests(writer: _Writer, rows: list[dict[str, Any]]) -> None:
    writer.set(("simulation_state", "quest_state", "quests"), rows)
    writer.set(("state", "quests"), deepcopy(rows))  # the play screen's projection


def _move_hero(writer: _Writer, change: LocationChanged) -> None:
    """Where the hero is, in every copy turn code and the play screen read (RQ-2.1: travel owns them all)."""
    location_id = change.location_id
    previous = str(writer.get(_PLAYER + ("location_id",)) or "")
    for path in (_PLAYER + ("location_id",), _PLAYER + ("current_location_id",), ("simulation_state", "location_id"),
                 ("simulation_state", "current_location_id"), ("simulation_state", "current_location")):
        writer.set(path, location_id)
    if previous and previous != location_id:
        writer.set(("simulation_state", "previous_location"), previous)
        visited = [str(place) for place in writer.get(("simulation_state", "visited_locations")) or ()]
        writer.set(("simulation_state", "visited_locations"),
                   [*visited, *(place for place in (previous, location_id) if place not in visited)])
    travel = writer.get(("simulation_state", "travel_state"))
    if isinstance(travel, dict):
        writer.set(("simulation_state", "travel_state"), {**travel, "current_location_id": location_id})
    party = writer.get(_PLAYER + ("party_state",))
    if isinstance(party, dict) and party.get("companions"):  # the party travels with the hero
        writer.set(_PLAYER + ("party_state",), {**party, "companions": [
            {**companion, "location_id": location_id} if isinstance(companion, dict) else companion
            for companion in party["companions"]]})
    place = _world_place(writer, location_id)
    if place:
        exits = place.get("exits") if isinstance(place.get("exits"), dict) else {}
        writer.set(("simulation_state", "location_state"), {"current_location_id": location_id,
                                                             "current_location": deepcopy(place),
                                                             "available_exits": dict(exits)})
        writer.set(("simulation_state", "present_npcs"), deepcopy(list(place.get("present_npcs") or [])))
    if not change.location_name:
        return
    name = change.location_name
    old_name = str(writer.get(("state", "current_location_name")) or writer.get(("state", "location")) or "")
    writer.set(("simulation_state", "current_location_name"), name)
    writer.set(("simulation_state", "location_name"), name)
    writer.set(("state", "current_location_id"), location_id)
    for key in ("current_location_name", "current_location", "location"):
        writer.set(("state", key), name)
    title = str(writer.get(("state", "title")) or "")
    if old_name and old_name != name and title.endswith(old_name):
        writer.set(("state", "title"), title[: len(title) - len(old_name)] + name)
    world = writer.get(("state", "world"))
    if isinstance(world, dict):
        world = {**world, "current_location_id": location_id, "current_location_name": name}
        region = str(place.get("region_id") or "")
        if region and isinstance(world.get("environment"), dict):
            world["environment"] = {**world["environment"], "region_id": region,
                                    "region_name": str(place.get("region_name") or "")}
            world["region"] = str(place.get("region_name") or world.get("region") or "")
        writer.set(("state", "world"), world)
    context = writer.get(("state", "scene", "environment_context"))
    if isinstance(context, dict):
        writer.set(("state", "scene", "environment_context"), {
            **context, "location_id": location_id, "location_label": name,
            "region_id": str(place.get("region_id") or context.get("region_id") or "")})


def _world_place(writer: _Writer, location_id: str) -> dict[str, Any]:
    places = writer.get(("simulation_state", "world_model", "locations"))
    place = places.get(location_id) if isinstance(places, dict) else None
    return dict(place) if isinstance(place, dict) else {}


def _apply(writer: _Writer, change: StateChange) -> None:  # noqa: C901 - one branch per change type
    if isinstance(change, PurseChanged):
        total = _copper(writer.get(_PLAYER + ("currency",)) or writer.get(_STORE + ("currency",))) + change.delta_copper
        if total < 0:
            raise ChangeRejected(f"the purse cannot pay {-change.delta_copper} copper")
        for path in (_PLAYER + ("currency",), _STORE + ("currency",), ("state", "player", "currency")):
            writer.set(path, _purse(total))
    elif isinstance(change, ItemAdded):
        items = _items(writer)
        _put(items, {**change.fields, "item_id": change.item_id, "name": change.name, "qty": change.quantity,
                     "category": change.category})
        _write_items(writer, items)
    elif isinstance(change, ItemRemoved):
        items = _items(writer)
        _take(items, change.item_id, change.quantity)
        _write_items(writer, items)
    elif isinstance(change, ItemDropped):
        items = _items(writer)
        taken = _take(items, change.item_id, change.quantity)
        ground = _ground(writer, change.location_id)
        _put(ground, taken)
        _write_items(writer, items)
        writer.set(("simulation_state", "world_items", "by_location", change.location_id), ground)
    elif isinstance(change, ItemPickedUp):
        ground = _ground(writer, change.location_id)
        taken = _take(ground, change.item_id, change.quantity)
        items = _items(writer)
        _put(items, taken)
        _write_items(writer, items)
        writer.set(("simulation_state", "world_items", "by_location", change.location_id), ground)
    elif isinstance(change, ItemEquipped):
        if not any(_key(item) == change.item_id for item in _items(writer)):
            raise ChangeRejected(f"the pack holds no {change.item_id} to equip")
        equipment = dict(writer.get(_STORE + ("equipment",)) or {})
        equipment[change.slot] = change.item_id
        writer.set(_STORE + ("equipment",), equipment)
    elif isinstance(change, ItemUnequipped):
        equipment = dict(writer.get(_STORE + ("equipment",)) or {})
        equipment.pop(change.slot, None)
        writer.set(_STORE + ("equipment",), equipment)
    elif isinstance(change, HpChanged):
        hp = dict(writer.get(_PLAYER + ("resources", "hp")) or {"current": 0, "max": 0})
        maximum = int(hp.get("max") or 0)
        hp["current"] = max(0, min(maximum, int(hp.get("current") or 0) + change.delta))
        writer.set(_PLAYER + ("resources", "hp"), hp)
        writer.set(("state", "player", "resources", "hp"), dict(hp))
    elif isinstance(change, ExperienceGained):
        writer.set(_PLAYER + ("xp",), int(writer.get(_PLAYER + ("xp",)) or 0) + change.amount)
    elif isinstance(change, SkillProgressed):
        skill = dict(writer.get(_PLAYER + ("skills", change.skill_id)) or {})
        skill.update(level=change.level, xp=change.xp, xp_to_next=change.xp_to_next)
        writer.set(_PLAYER + ("skills", change.skill_id), skill)
    elif isinstance(change, LocationChanged):
        _move_hero(writer, change)
    elif isinstance(change, PresenceChanged):
        writer.set(("simulation_state", "present_npc_state"),
                   {**dict(writer.get(("simulation_state", "present_npc_state")) or {}),
                    "location_id": change.location_id, "present_npc_ids": list(change.present_npc_ids)})
        writer.set(("runtime_state", "current_scene", "present_npc_ids"), list(change.present_npc_ids))
        place = _world_place(writer, change.location_id)
        if place:  # the scene the narrator and the scene readers build on is the place the hero is in
            scene = writer.get(("runtime_state", "current_scene"))
            name = str(place.get("name") or change.location_id)
            writer.set(("runtime_state", "current_scene"), {
                **(scene if isinstance(scene, dict) else {}), "scene_id": f"scene:{change.location_id}",
                "location_id": change.location_id, "location_name": name, "title": name,
                "summary": str(place.get("description") or name), "present_npc_ids": list(change.present_npc_ids),
                "actors": [str(npc.get("name") or "") for npc in place.get("present_npcs") or () if isinstance(npc, dict)]})
    elif isinstance(change, TimeAdvanced):
        writer.set(("simulation_state", "tick"), int(writer.get(("simulation_state", "tick")) or 0) + change.ticks)
    elif isinstance(change, TurnCounted):
        for path in (("manifest", "turn_count"), ("manifest", "current_turn"), ("state", "turn_count"),
                     ("state", "current_turn")):
            writer.set(path, change.turn_count)
    elif isinstance(change, WorldTicked):
        for key, value in change.simulation.items():
            writer.set(("simulation_state", key), value)
        for key, value in change.runtime.items():
            writer.set(("runtime_state", key), value)
        environment = change.simulation.get("environment")
        if isinstance(environment, dict) and isinstance(writer.get(("state", "world")), dict):
            # The one clock is the simulation's environment; the play screen reads its copy and label.
            minutes = max(0, int(environment.get("absolute_minutes") or 0))
            writer.set(("state", "world", "environment"), environment)
            writer.set(("state", "world", "time"),
                       f"Day {minutes // 1440 + 1} • {minutes % 1440 // 60:02d}:{minutes % 60:02d}")
    elif isinstance(change, ServiceReserved):
        reserved = [dict(service) for service in writer.get(("simulation_state", "active_services")) or ()
                    if isinstance(service, dict)]
        reserved.append({"service_id": change.offer_id, "offer_id": change.offer_id, "service_kind": change.service_kind,
                         "provider_id": change.provider_id, "provider_name": change.provider_name,
                         "label": change.label, "duration": change.duration, "status": "active",
                         "started_tick": int(writer.get(("simulation_state", "tick")) or 0),
                         "effects": {"duration": change.duration, f"{change.service_kind}_reserved": True}})
        writer.set(("simulation_state", "active_services"), reserved)
    elif isinstance(change, StockTaken):
        writer.set(("simulation_state", "trade", "stock", change.offer_id), change.remaining)
    elif isinstance(change, TradeRemembered):
        ledger = [dict(row) for row in writer.get(("simulation_state", "trade", "ledger")) or () if isinstance(row, dict)]
        ledger.append({"provider_id": change.provider_id, "provider_name": change.provider_name, "deal": change.deal,
                       "what": change.what, "copper": change.copper,
                       "tick": int(writer.get(("simulation_state", "tick")) or 0)})
        writer.set(("simulation_state", "trade", "ledger"), ledger[-TRADE_LEDGER_KEPT:])
    elif isinstance(change, JournalWritten):
        writer.set(("runtime_state", "campaign_calendar"), change.calendar)
        writer.set(("runtime_state", "player_journal"), change.journal)
    elif isinstance(change, NeedsChanged):
        survival = dict(writer.get(("simulation_state", "survival")) or {})
        for need in ("hunger", "thirst", "fatigue"):
            survival[need] = max(0, int(survival.get(need) or 0) + getattr(change, need))
        writer.set(("simulation_state", "survival"), survival)
    elif isinstance(change, QuestStatusChanged):
        rows, index = _quest_rows(writer, change.quest_id)
        rows[index] = {**rows[index], "status": change.status}
        _write_quests(writer, rows)
    elif isinstance(change, QuestPlaceReached):
        rows, index = _quest_rows(writer, change.quest_id)
        visited = list(rows[index].get("visited_locations") or [])
        if change.location_id not in visited:
            visited.append(change.location_id)
        rows[index] = {**rows[index], "visited_locations": visited}
        _write_quests(writer, rows)
    elif isinstance(change, CompanionJoined):
        party = dict(writer.get(_PLAYER + ("party_state",)) or {})
        companions = [dict(row) for row in party.get("companions") or ()]
        if any(row.get("npc_id") == change.npc_id for row in companions):
            raise ChangeRejected(f"{change.npc_id} is already in the party")
        if len(companions) >= int(party.get("max_size") or 3):
            raise ChangeRejected("the party is full")
        companions.append({"npc_id": change.npc_id, "name": change.name, "role": change.role, "hp": 100,
                           "max_hp": 100, "status": "active", "follow_mode": "following_player"})
        writer.set(_PLAYER + ("party_state",), {**party, "companions": companions, "max_size": party.get("max_size", 3)})
    elif isinstance(change, CompanionLeft):
        party = dict(writer.get(_PLAYER + ("party_state",)) or {})
        companions = [dict(row) for row in party.get("companions") or () if row.get("npc_id") != change.npc_id]
        writer.set(_PLAYER + ("party_state",), {**party, "companions": companions})
    elif isinstance(change, CombatStarted):
        combat = writer.get(("simulation_state", "combat_state"))
        if isinstance(combat, dict) and combat.get("active"):
            raise ChangeRejected("a fight is already on")
        writer.set(("simulation_state", "combat_state"), {
            "active": True, "combat_id": change.combat_id, "round": 1, "current_actor_id": "player",
            "participants": {actor: {"hp": hp, "max_hp": hp} for actor, hp in sorted(change.participants.items())},
        })
    elif isinstance(change, CombatantHpChanged):
        participant = writer.get(("simulation_state", "combat_state", "participants", change.actor_id))
        if not isinstance(participant, dict):
            raise ChangeRejected(f"{change.actor_id} is not in the fight")
        maximum = int(participant.get("max_hp") or participant.get("hp") or 0)
        hp = max(0, min(maximum, int(participant.get("hp") or 0) + change.delta))
        writer.set(("simulation_state", "combat_state", "participants", change.actor_id), {**participant, "hp": hp})
    elif isinstance(change, CombatEnded):
        combat = writer.get(("simulation_state", "combat_state"))
        if not isinstance(combat, dict) or not combat.get("active"):
            raise ChangeRejected("there is no fight to end")
        writer.set(("simulation_state", "combat_state"), {**combat, "active": False, "outcome": change.outcome})
    else:  # pragma: no cover - the vocabulary is closed
        raise ChangeRejected(f"unknown change {change!r}")


def reduce(document: dict[str, Any], changes: list[StateChange]) -> tuple[dict[str, Any], JsonPatch]:
    """The document with ``changes`` applied (a copy; ``document`` is unchanged), and the patch of the writes."""
    writer = _Writer(deepcopy(document))
    for change in changes:
        _apply(writer, change)
    return writer.document, writer.patch()
