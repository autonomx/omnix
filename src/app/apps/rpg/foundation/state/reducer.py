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

from app.apps.rpg.foundation.safe_values import copy_state

from .changes import (
    CombatantHpChanged,
    CombatStarted,
    CombatEnded,
    CompanionJoined,
    CompanionLeft,
    CompanionOrdered,
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
    QuestProgressed,
    QuestStatusChanged,
    QuestStepCompleted,
    SkillProgressed,
    StateChange,
    ConditionsChanged,
    DialogueExchanged,
    KnowledgeShared,
    QuestOffered,
    PressuresMoved,
    CombatAdvanced,
    CompanionHpChanged,
    LevelReached,
    DefeatRecorded,
    CampaignEnded,
    JournalWritten,
    RestTaken,
    ServiceReserved,
    ServiceUsed,
    StockTaken,
    TimeAdvanced,
    TradeRemembered,
    TurnCounted,
    AbilityUsed,
    CheckResolved,
    HotbarChanged,
    InteractionPresented,
    InteractionRecorded,
    InteractionsReplayed,
    LifecycleRecorded,
    MapStateProjected,
    LevelChoiceMade,
    LocalMapEntered,
    RegardChanged,
    RevisionRestored,
    ResourcesChanged,
    WhereaboutsChanged,
    WorldTicked,
)

JsonPatch = list[dict[str, Any]]
TRADE_LEDGER_KEPT = 50
DIALOGUE_EXCHANGES_KEPT = 8
_PLAYER = ("simulation_state", "player_state")
_STORE = _PLAYER + ("inventory_state",)
# Where gear is worn (the store's slots, which combat reads) and what the play screen's sheet calls each.
SLOT_LABELS = {"main_hand": "Weapon", "off_hand": "Shield", "body": "Armor", "head": "Helmet", "cloak": "Cloak",
               "ring": "Ring", "tool": "Tool"}


CHECKS_KEPT = 20  # the recent checks a retry is judged against (checks.md)


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
        item = next((item for item in _items(writer) if _key(item) == change.item_id), None)
        if item is None:
            raise ChangeRejected(f"the pack holds no {change.item_id} to equip")
        equipment = dict(writer.get(_STORE + ("equipment",)) or {})
        equipment[change.slot] = change.item_id
        writer.set(_STORE + ("equipment",), equipment)
        _show_worn(writer, change.slot, str(item.get("name") or change.item_id))
    elif isinstance(change, ItemUnequipped):
        equipment = dict(writer.get(_STORE + ("equipment",)) or {})
        equipment.pop(change.slot, None)
        writer.set(_STORE + ("equipment",), equipment)
        _show_worn(writer, change.slot, "")
    elif isinstance(change, HpChanged):
        hp = dict(writer.get(_PLAYER + ("resources", "hp")) or {"current": 0, "max": 0})
        maximum = int(hp.get("max") or 0)
        hp["current"] = max(0, min(maximum, int(hp.get("current") or 0) + change.delta))
        writer.set(_PLAYER + ("resources", "hp"), hp)
        writer.set(_PLAYER + ("hp",), hp["current"])
        writer.set(("state", "player", "resources", "hp"), dict(hp))
    elif isinstance(change, ExperienceGained):
        xp = int(writer.get(_PLAYER + ("xp",)) or 0) + change.amount
        writer.set(_PLAYER + ("xp",), xp)
        _show_progression(writer, xp=xp)
    elif isinstance(change, LevelReached):
        for key in ("level", "xp", "xp_to_next", "unspent_points", "unspent_skill_points"):
            writer.set(_PLAYER + (key,), getattr(change, key))
        writer.set(_PLAYER + ("level_choices_pending",), change.choices_pending)
        if change.max_hp_gain:  # each level adds to the hero's health, and heals them by as much
            hp = dict(writer.get(_PLAYER + ("resources", "hp")) or {"current": 0, "max": 0})
            hp = {**hp, "max": int(hp.get("max") or 0) + change.max_hp_gain,
                  "current": int(hp.get("current") or 0) + change.max_hp_gain}
            writer.set(_PLAYER + ("resources", "hp"), hp)
            writer.set(_PLAYER + ("hp",), hp["current"])
            writer.set(_PLAYER + ("max_hp",), hp["max"])
            if isinstance(writer.get(("state", "player")), dict):
                writer.set(("state", "player", "resources", "hp"), dict(hp))
        if isinstance(writer.get(("state", "player")), dict):
            writer.set(("state", "player", "level_choices_pending"), change.choices_pending)
        _show_progression(writer, xp=change.xp, xp_to_next=change.xp_to_next, level=change.level)
    elif isinstance(change, LevelChoiceMade):
        _make_level_choice(writer, change)
    elif isinstance(change, RevisionRestored):
        _restore(writer, change)
    elif isinstance(change, SkillProgressed):
        skill = dict(writer.get(_PLAYER + ("skills", change.skill_id)) or {})
        skill.update(level=change.level, xp=change.xp, xp_to_next=change.xp_to_next)
        writer.set(_PLAYER + ("skills", change.skill_id), skill)
        if isinstance(writer.get(("state", "player")), dict):  # the play screen's sheet shows it
            writer.set(("state", "player", "skills", change.skill_id), dict(skill))
    elif isinstance(change, LocationChanged):
        _move_hero(writer, change)
    elif isinstance(change, LocalMapEntered):
        writer.set(("state", "current_map_instance_id"), change.map_instance_id)
    elif isinstance(change, PresenceChanged):
        writer.set(("simulation_state", "present_npc_state"),
                   {**dict(writer.get(("simulation_state", "present_npc_state")) or {}),
                    "location_id": change.location_id, "present_npc_ids": list(change.present_npc_ids)})
        writer.set(("runtime_state", "current_scene", "present_npc_ids"), list(change.present_npc_ids))
        place = _world_place(writer, change.location_id)
        if place:  # the scene the narrator and the scene readers build on is the place the hero is in
            people = writer.get(("simulation_state", "world_model", "npcs"))
            people = people if isinstance(people, dict) else {}
            here = [{"id": npc_id, "name": str((people.get(npc_id) or {}).get("name") or npc_id),
                     "role": str((people.get(npc_id) or {}).get("role") or "")} for npc_id in change.present_npc_ids]
            writer.set(("simulation_state", "present_npcs"), here)
            scene = writer.get(("runtime_state", "current_scene"))
            name = str(place.get("name") or change.location_id)
            writer.set(("runtime_state", "current_scene"), {
                **(scene if isinstance(scene, dict) else {}), "scene_id": f"scene:{change.location_id}",
                "location_id": change.location_id, "location_name": name, "title": name,
                "summary": str(place.get("description") or name), "present_npc_ids": list(change.present_npc_ids),
                "actors": [person["name"] for person in here]})
    elif isinstance(change, ResourcesChanged):
        for name, delta in (("stamina", change.stamina), ("mana", change.mana)):
            if not delta:
                continue
            pool = writer.get(_PLAYER + ("resources", name)) or writer.get(("state", "player", "resources", name))
            pool = dict(pool) if isinstance(pool, dict) else {"current": 0, "max": 0}
            pool["current"] = max(0, min(int(pool.get("max") or 0), int(pool.get("current") or 0) + delta))
            writer.set(_PLAYER + ("resources", name), pool)
            if isinstance(writer.get(("state", "player")), dict):  # the play screen's sheet shows it
                writer.set(("state", "player", "resources", name), dict(pool))
    elif isinstance(change, MapStateProjected):
        writer.set(("state", "map_state"), deepcopy(change.map_state))
        writer.set(("state", "current_location_id"), change.location_id)
        if isinstance(writer.get(("state", "player")), dict):
            writer.set(("state", "player", "location_id"), change.location_id)
    elif isinstance(change, InteractionRecorded):
        _record_interaction(writer, change.event)
    elif isinstance(change, InteractionsReplayed):
        _replay_interactions(writer, change.events)
    elif isinstance(change, LifecycleRecorded):
        _record_lifecycle(writer, change)
    elif isinstance(change, InteractionPresented):
        _present_interaction(writer, change)
    elif isinstance(change, HotbarChanged):
        # The hotbar is the sheet's (``state.hotbar``), mirrored in the ability state the play screen also reads.
        hotbar = {str(slot): str(ability) for slot, ability in dict(writer.get(("state", "hotbar")) or {}).items()}
        if change.ability_id:
            hotbar[change.slot] = change.ability_id
        else:
            hotbar.pop(change.slot, None)
        writer.set(("state", "hotbar"), hotbar)
        writer.set(("state", "ability_state", "hotbar"), dict(hotbar))
    elif isinstance(change, AbilityUsed):
        ready = dict(writer.get(("state", "ability_state", "ready_at")) or {})
        ready[change.ability_id] = change.ready_at_turn
        writer.set(("state", "ability_state", "ready_at"), ready)
        _show_cooldowns(writer)
    elif isinstance(change, CheckResolved):
        checks = writer.get(("simulation_state", "checks"))
        checks = dict(checks) if isinstance(checks, dict) else {}
        record = {**change.model_dump(mode="json", exclude={"type"}),
                  "tick": int(writer.get(("simulation_state", "tick")) or 0)}
        history = [row for row in checks.get("history") or () if isinstance(row, dict)]
        writer.set(("simulation_state", "checks"), {"last": record, "history": [*history, record][-CHECKS_KEPT:]})
    elif isinstance(change, RegardChanged):
        kept = writer.get(("simulation_state", "relationship_state", change.npc_id))
        kept = dict(kept) if isinstance(kept, dict) else {}
        trust = max(-100, min(100, int(kept.get("trust") or kept.get("score") or 0) + change.delta))
        writer.set(("simulation_state", "relationship_state", change.npc_id), {**kept, "trust": trust})
        _show_regard(writer, change.name or change.npc_id, trust)
    elif isinstance(change, WhereaboutsChanged):
        for person in change.people:  # the npcs section's index: where each is, doing what
            kept = writer.get(("simulation_state", "npc_index", person.npc_id))
            writer.set(("simulation_state", "npc_index", person.npc_id), {
                **(kept if isinstance(kept, dict) else {"npc_id": person.npc_id}),
                "location_id": person.location_id, "activity": person.activity})
    elif isinstance(change, TimeAdvanced):
        writer.set(("simulation_state", "tick"), int(writer.get(("simulation_state", "tick")) or 0) + change.ticks)
    elif isinstance(change, TurnCounted):
        for path in (("manifest", "turn_count"), ("manifest", "current_turn"), ("state", "turn_count"),
                     ("state", "current_turn")):
            writer.set(path, change.turn_count)
        if writer.get(("state", "ability_state", "ready_at")):
            _show_cooldowns(writer)  # each counted turn brings the hero's abilities nearer to ready
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
    elif isinstance(change, ConditionsChanged):
        conditions = [dict(condition) for condition in change.conditions]
        if change.actor_id == "player":
            writer.set(_PLAYER + ("conditions",), conditions)
        else:
            party = dict(writer.get(_PLAYER + ("party_state",)) or {})
            companions = [dict(row) for row in party.get("companions") or () if isinstance(row, dict)]
            if not any(row.get("npc_id") == change.actor_id for row in companions):
                raise ChangeRejected(f"{change.actor_id} is not in the party")
            party["companions"] = [{**row, "conditions": conditions} if row.get("npc_id") == change.actor_id else row
                                   for row in companions]
            writer.set(_PLAYER + ("party_state",), party)
    elif isinstance(change, RestTaken):
        writer.set(_PLAYER + ("rest_point",), change.location_id)
    elif isinstance(change, ServiceUsed):
        services = [dict(row) for row in writer.get(("simulation_state", "active_services")) or () if isinstance(row, dict)]
        index = next((i for i, row in enumerate(services)
                      if row.get("offer_id") == change.offer_id and row.get("status") == "active"), None)
        if index is None:
            raise ChangeRejected(f"no {change.offer_id} is kept to use")
        services[index] = {**services[index], "status": "consumed",
                           "consumed_tick": int(writer.get(("simulation_state", "tick")) or 0)}
        writer.set(("simulation_state", "active_services"), services)
    elif isinstance(change, StockTaken):
        writer.set(("simulation_state", "trade", "stock", change.offer_id), {"remaining": change.remaining,
                                                                            "day": change.day})
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
        if change.status == "active" and rows[index].get("accepted_at_minute") is None:
            # When it was taken up, on the campaign clock: a quest's deadline runs from here (quests.md).
            environment = writer.get(("simulation_state", "environment"))
            minutes = environment.get("absolute_minutes") if isinstance(environment, dict) else None
            rows[index]["accepted_at_minute"] = int(minutes or 0)
        _write_quests(writer, rows)
    elif isinstance(change, QuestStepCompleted):
        rows, index = _quest_rows(writer, change.quest_id)
        progress = dict(rows[index].get("progress") or {})
        branches = list(progress.get("branches") or [])
        if change.branch is not None:
            branches.append({"stage": change.stage - 1, "branch": change.branch})
        rows[index] = {**rows[index], "progress": {**progress, "stage": change.stage, "branches": branches},
                       **({"objective": change.next_objective} if change.next_objective else {})}
        _write_quests(writer, rows)
    elif isinstance(change, QuestProgressed):
        rows, index = _quest_rows(writer, change.quest_id)
        rows[index] = {**rows[index], "progress": {**dict(rows[index].get("progress") or {}),
                                                   "counts": dict(change.counts)}}
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
    elif isinstance(change, CompanionOrdered):
        party = dict(writer.get(_PLAYER + ("party_state",)) or {})
        companions = [dict(row) for row in party.get("companions") or () if isinstance(row, dict)]
        if not any(row.get("npc_id") == change.npc_id for row in companions):
            raise ChangeRejected(f"{change.npc_id} is not in the party")
        party["companions"] = [{**row, "orders": change.order, "stance": change.stance or row.get("stance", "")}
                               if row.get("npc_id") == change.npc_id else row for row in companions]
        writer.set(_PLAYER + ("party_state",), party)
    elif isinstance(change, DialogueExchanged):
        exchanges = [dict(row) for row in writer.get(("simulation_state", "dialogue", "exchanges", change.npc_id)) or ()
                     if isinstance(row, dict)]
        exchanges.append({"player": change.player_line, "npc": change.npc_line,
                          "tick": int(writer.get(("simulation_state", "tick")) or 0)})
        writer.set(("simulation_state", "dialogue", "exchanges", change.npc_id), exchanges[-DIALOGUE_EXCHANGES_KEPT:])
        writer.set(("runtime_state", "dialogue_focus"), {"target_id": change.npc_id, "target_name": change.name,
                                                         "tick": int(writer.get(("simulation_state", "tick")) or 0)})
    elif isinstance(change, KnowledgeShared):
        known = [str(fact) for fact in writer.get(("simulation_state", "dialogue", "known_facts", change.npc_id)) or ()]
        if change.fact_id not in known:
            writer.set(("simulation_state", "dialogue", "known_facts", change.npc_id), [*known, change.fact_id])
    elif isinstance(change, QuestOffered):
        quests = writer.get(("simulation_state", "quest_state", "quests"))
        known = isinstance(quests, list) and any(
            isinstance(row, dict) and change.quest_id in (row.get("quest_id"), row.get("id")) for row in quests)
        if not known and change.quest:  # a new quest: its row joins the log
            _write_quests(writer, [*(dict(row) for row in quests or ()), {**change.quest, "quest_id": change.quest_id}])
        rows, index = _quest_rows(writer, change.quest_id)
        rows[index] = {**rows[index], "offered_by": change.npc_id}
        _write_quests(writer, rows)
    elif isinstance(change, PressuresMoved):
        if change.runtime:
            writer.set(("simulation_state", "causal_world_runtime"), change.runtime)
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
    elif isinstance(change, CombatAdvanced):
        writer.set(("simulation_state", "combat_state"), deepcopy(change.combat_state))
    elif isinstance(change, CompanionHpChanged):
        party = dict(writer.get(_PLAYER + ("party_state",)) or {})
        companions = [dict(row) for row in party.get("companions") or () if isinstance(row, dict)]
        if not any(row.get("npc_id") == change.npc_id for row in companions):
            raise ChangeRejected(f"{change.npc_id} is not in the party")
        party["companions"] = [{**row, "hp": min(change.hp, int(row.get("max_hp") or change.hp))}
                               if row.get("npc_id") == change.npc_id else row for row in companions]
        writer.set(_PLAYER + ("party_state",), party)
    elif isinstance(change, DefeatRecorded):
        writer.set(_PLAYER + ("defeats",), change.defeats)
    elif isinstance(change, CampaignEnded):
        writer.set(("simulation_state", "campaign_end"), {
            "ended": True, "reason": change.reason, "defeated_by": list(change.defeated_by),
            "tick": int(writer.get(("simulation_state", "tick")) or 0)})
    else:  # pragma: no cover - the vocabulary is closed
        raise ChangeRejected(f"unknown change {change!r}")


def _restore(writer: _Writer, change: RevisionRestored) -> None:
    """The earlier document's game, put back: the sheet and the simulation whole, the runtime sections a section
    owns, and the turn count; the rest of the runtime (bookkeeping, narrations) is the campaign's as it is now."""
    from app.apps.rpg.foundation.state.sections import SECTION_PATHS

    earlier = change.document
    for key in ("state", "simulation_state"):
        if isinstance(earlier.get(key), dict):
            writer.set((key,), deepcopy(earlier[key]))
    # The game's runtime sections; the interactions section is the campaign's bookkeeping, which goes on.
    game_runtime = {path[1] for name, paths in SECTION_PATHS.items() if name != "interactions"
                    for path in paths if path[0] == "runtime_state"}
    runtime = dict(writer.get(("runtime_state",)) or {})
    before = earlier.get("runtime_state") if isinstance(earlier.get("runtime_state"), dict) else {}
    for key in game_runtime:
        runtime.pop(key, None)
        if key in before:
            runtime[key] = deepcopy(before[key])
    writer.set(("runtime_state",), runtime)
    manifest = earlier.get("manifest") if isinstance(earlier.get("manifest"), dict) else {}
    for key in ("turn_count", "current_turn"):
        if key in manifest:
            writer.set(("manifest", key), manifest[key])


def _make_level_choice(writer: _Writer, change: LevelChoiceMade) -> None:
    pending = int(writer.get(_PLAYER + ("level_choices_pending",)) or 0)
    if pending <= 0:
        raise ChangeRejected("no level's choice is waiting")
    writer.set(_PLAYER + ("level_choices_pending",), pending - 1)
    sheet = isinstance(writer.get(("state", "player")), dict)
    if sheet:
        writer.set(("state", "player", "level_choices_pending"), pending - 1)
    if change.choice == "attribute":
        writer.set(_PLAYER + ("stats", change.attribute), change.value)
        if sheet:
            writer.set(("state", "player", "stats", change.attribute), change.value)
    elif change.choice == "ability":
        unlocked = [str(item) for item in writer.get(("state", "ability_state", "unlocked")) or ()]
        writer.set(("state", "ability_state", "unlocked"), [*unlocked, change.ability_id])
        ranks = dict(writer.get(("state", "ability_state", "ranks")) or {})
        writer.set(("state", "ability_state", "ranks"), {**ranks, change.ability_id: 1})
    else:
        for skill_id in change.skills:
            skill = dict(writer.get(_PLAYER + ("skills", skill_id)) or {})
            skill["level"] = min(5, int(skill.get("level") or 0) + 1)
            writer.set(_PLAYER + ("skills", skill_id), skill)
            if sheet:
                writer.set(("state", "player", "skills", skill_id), dict(skill))


def _show_cooldowns(writer: _Writer) -> None:
    """The play screen's cooldowns: the hero's turns left before each ability is ready again."""
    turn = int(writer.get(("state", "turn_count")) or 0)
    ready = writer.get(("state", "ability_state", "ready_at")) or {}
    writer.set(("state", "ability_state", "cooldowns"),
               {str(ability_id): int(at) - turn - 1 for ability_id, at in ready.items() if int(at) - turn - 1 > 0})


def _show_regard(writer: _Writer, name: str, trust: int) -> None:
    """The play screen's relationships list: the person's standing with the hero, as the sheet words it."""
    rows = writer.get(("state", "relationships"))
    if not isinstance(writer.get(("state",)), dict):
        return
    rows = [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    stance = "Friendly" if trust >= 50 else "Hostile" if trust <= -50 else "Wary" if trust < 0 else "Neutral"
    entry = {"name": name, "stance": stance, "score": trust}
    rows = [entry if row.get("name") == name else row for row in rows]
    writer.set(("state", "relationships"), rows if entry in rows else [*rows, entry])


def _show_worn(writer: _Writer, slot: str, name: str) -> None:
    """The sheet's list of worn gear, as the store has it (``name`` empty: the slot is bare)."""
    sheet = writer.get(("state", "player"))
    if not isinstance(sheet, dict):
        return
    label = SLOT_LABELS.get(slot, slot.replace("_", " ").title())
    worn = [dict(row) for row in sheet.get("equipment") or () if isinstance(row, dict)
            and str(row.get("slot") or "").casefold() != label.casefold()]
    writer.set(("state", "player", "equipment"), [*worn, {"slot": label, "name": name}] if name else worn)


def _unequip_gone(writer: _Writer) -> None:
    """Gear no longer carried is no longer worn."""
    equipment = writer.get(_STORE + ("equipment",))
    if not isinstance(equipment, dict) or not equipment:
        return
    carried = {_key(item) for item in _items(writer) if _quantity(item) > 0}
    for slot, item_id in list(equipment.items()):
        if str(item_id) not in carried:
            equipment = {key: value for key, value in equipment.items() if key != slot}
            writer.set(_STORE + ("equipment",), equipment)
            _show_worn(writer, slot, "")


def _show_progression(writer: _Writer, *, xp: int, xp_to_next: int | None = None, level: int | None = None) -> None:
    """The play screen's sheet shows the hero's experience and level as the simulation keeps them."""
    sheet = writer.get(("state", "player"))
    if not isinstance(sheet, dict):
        return
    meter = sheet.get("xp") if isinstance(sheet.get("xp"), dict) else {}
    writer.set(("state", "player", "xp"), {**meter, "current": xp,
                                           "max": xp_to_next or int(meter.get("max") or 0) or 100})
    if level is not None:
        writer.set(("state", "player", "level"), level)


_RUNTIME = ("runtime_state",)
TIMELINE_KEPT, RECENT_INTERACTIONS_KEPT, LIFECYCLES_KEPT = 50, 12, 64


def _kept_last(mapping: dict[str, Any], count: int) -> dict[str, Any]:
    return dict(list(mapping.items())[-count:])


def _show_timeline(writer: _Writer, timeline: dict[str, Any], events: list[dict[str, Any]]) -> None:
    """The timeline written with its events, and the recent and last interactions it shows."""
    timeline["events"] = events
    writer.set(_RUNTIME + ("interaction_timeline",), timeline)
    writer.set(_RUNTIME + ("recent_interactions",), deepcopy(events[-RECENT_INTERACTIONS_KEPT:]))
    if events:
        writer.set(_RUNTIME + ("last_interaction",), deepcopy(events[-1]))


def _record_interaction(writer: _Writer, event: dict[str, Any]) -> None:
    timeline = dict(writer.get(_RUNTIME + ("interaction_timeline",)) or {})
    events = [deepcopy(row) for row in timeline.get("events") or () if isinstance(row, dict)]
    events = [*events, deepcopy(event)][-TIMELINE_KEPT:]
    timeline.update(format_version=event.get("format_version") or timeline.get("format_version"),
                    last_sequence=event.get("sequence"), state_revision=event.get("state_revision"))
    writer.set(_RUNTIME + ("interaction_seq",), event.get("sequence"))
    writer.set(_RUNTIME + ("state_revision",), event.get("state_revision"))
    _show_timeline(writer, timeline, events)


def _replay_interactions(writer: _Writer, replayed: list[dict[str, Any]]) -> None:
    timeline = dict(writer.get(_RUNTIME + ("interaction_timeline",)) or {})
    by_id = {str(row.get("interaction_id") or f"sequence:{row.get('sequence')}"): dict(row)
             for row in timeline.get("events") or () if isinstance(row, dict)}
    for row in replayed:
        by_id[str(row.get("interaction_id") or f"sequence:{row.get('sequence')}")] = dict(row)
    events = sorted(by_id.values(), key=lambda row: int(row.get("sequence") or 0))[-TIMELINE_KEPT:]
    last = events[-1] if events else {}
    sequence = int(last.get("sequence") or timeline.get("last_sequence") or 0)
    revision = int(last.get("state_revision") or timeline.get("state_revision") or 0)
    timeline.update(format_version="rpg_interaction_timeline_v1", last_sequence=sequence, state_revision=revision)
    writer.set(_RUNTIME + ("interaction_seq",), max(int(writer.get(_RUNTIME + ("interaction_seq",)) or 0), sequence))
    writer.set(_RUNTIME + ("state_revision",), max(int(writer.get(_RUNTIME + ("state_revision",)) or 0), revision))
    _show_timeline(writer, timeline, events)


def _record_lifecycle(writer: _Writer, change: LifecycleRecorded) -> None:
    lifecycles = dict(writer.get(_RUNTIME + ("interaction_lifecycles",)) or {})
    lifecycles[change.interaction_id] = deepcopy(change.lifecycle)
    writer.set(_RUNTIME + ("interaction_lifecycles",), _kept_last(lifecycles, LIFECYCLES_KEPT))
    if change.turn_id:
        by_turn = dict(writer.get(_RUNTIME + ("interaction_id_by_turn",)) or {})
        by_turn[change.turn_id] = change.interaction_id
        writer.set(_RUNTIME + ("interaction_id_by_turn",), _kept_last(by_turn, LIFECYCLES_KEPT))
    timeline = dict(writer.get(_RUNTIME + ("interaction_timeline",)) or {})
    events = []
    for value in timeline.get("events") if isinstance(timeline.get("events"), list) else ():
        event = dict(value) if isinstance(value, dict) else {}
        if str(event.get("interaction_id") or "") == change.interaction_id:
            event["lifecycle"] = deepcopy(change.lifecycle)
            enrichment = change.lifecycle.get("narration_enrichment")
            if isinstance(enrichment, dict) and enrichment:
                event["narration_enrichment"] = dict(enrichment)
        events.append(event)
    _show_timeline(writer, timeline, events)


def _present_interaction(writer: _Writer, change: InteractionPresented) -> None:
    interactions = writer.get(_RUNTIME + ("recent_interactions",))
    if not isinstance(interactions, list) or not interactions:
        raise ChangeRejected("no recent interaction to present")
    rows = [dict(row) if isinstance(row, dict) else row for row in interactions]
    index = next((at for at in range(len(rows) - 1, -1, -1) if isinstance(rows[at], dict) and (
        (change.turn_id and str(rows[at].get("turn_id") or "") == change.turn_id)
        or (change.response_id and str(rows[at].get("narrative_response_id") or "") == change.response_id))),
        len(rows) - 1)
    if not isinstance(rows[index], dict):
        raise ChangeRejected("the recent interaction is no record")
    rows[index] = {**rows[index], **deepcopy(change.fields)}
    writer.set(_RUNTIME + ("recent_interactions",), rows)


def reduce(document: dict[str, Any], changes: list[StateChange], *,
           owned: bool = False) -> tuple[dict[str, Any], JsonPatch]:
    """The document with ``changes`` applied, and the patch of the writes. It is a copy, ``document`` unchanged;
    a caller that owns ``document`` (a copy made for the turn, the commit's own) passes ``owned`` and it is changed
    in place, saving the copy (RQ-6.4)."""
    writer = _Writer(document if owned else copy_state(document))  # a deep copy, about 2.5x faster than deepcopy
    for change in changes:
        _apply(writer, change)
        if isinstance(change, (ItemRemoved, ItemDropped)):
            _unequip_gone(writer)
    return writer.document, writer.patch()
