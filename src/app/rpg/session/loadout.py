"""Deterministic inventory, equipment, and ability actions for RPG sessions."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel

from app.rpg.session.ability_coverage import write_ability_coverage_snapshot
from app.rpg.session.ability_system import (
    apply_ability_to_state,
    assign_ability_to_hotbar,
    build_progression_package,
    remove_hotbar_slot,
    unlock_ability_in_state,
    upgrade_ability_rank_in_state,
)
from app.rpg.session.crafting import craft_from_inventory
from app.rpg.session.inventory_items import (
    consume_inventory_item,
    find_inventory_item,
    inventory_quantity,
    is_protected_item,
    merge_inventory_stack,
    normalize_player_inventory,
    set_inventory_quantity,
)
from app.rpg.session.item_materials import salvage_item
from app.rpg.session.item_use import use_inventory_item
from app.rpg.session.service import load_session, save_session
from app.rpg.session.world_ability_integration import apply_world_scale_loadout_ability, ensure_world_scale_abilities

LoadoutActionKind = Literal[
    "inspect",
    "use",
    "equip",
    "drop",
    "salvage",
    "craft",
    "use_ability",
    "hotbar",
    "unlock_ability",
    "upgrade_ability",
    "assign_hotbar",
    "remove_hotbar",
]


class RpgLoadoutActionRequest(BaseModel):
    action: LoadoutActionKind
    item_name: str | None = None
    recipe_id: str | None = None
    recipe_name: str | None = None
    station: str | None = None
    ability_id: str | None = None
    ability_name: str | None = None
    hotbar_slot: str | int | None = None
    target: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _norm(value: Any) -> str:
    return str(value or "").strip().casefold()


def _title(value: Any) -> str:
    return str(value or "").strip()


def _state(session: dict[str, Any]) -> dict[str, Any]:
    state = _safe_dict(session.get("state"))
    session["state"] = state
    return state


def _player(state: dict[str, Any]) -> dict[str, Any]:
    player = _safe_dict(state.get("player"))
    state["player"] = player
    return player


def _metric(player: dict[str, Any], key: str) -> dict[str, Any]:
    resources = _safe_dict(player.get("resources"))
    player["resources"] = resources
    metric = _safe_dict(resources.get(key))
    resources[key] = metric
    metric.setdefault("current", 0)
    metric.setdefault("max", metric.get("current", 0))
    return metric


def _change_metric(player: dict[str, Any], key: str, delta: int) -> tuple[int, int]:
    metric = _metric(player, key)
    current = int(metric.get("current") or 0)
    maximum = int(metric.get("max") or current)
    metric["current"] = max(0, min(maximum, current + delta))
    return int(metric["current"]), maximum


def _inventory(player: dict[str, Any]) -> list[dict[str, Any]]:
    return normalize_player_inventory(player)["inventory"]


def _find_item(player: dict[str, Any], item_name: str | None) -> tuple[list[dict[str, Any]], int, dict[str, Any] | None]:
    return find_inventory_item(player, item_name)


def _quantity(item: dict[str, Any]) -> int:
    return inventory_quantity(item)


def _set_quantity(inventory: list[dict[str, Any]], index: int, quantity: int) -> None:
    set_inventory_quantity(inventory, index, quantity)


def _consume(inventory: list[dict[str, Any]], index: int, amount: int = 1) -> None:
    consume_inventory_item(inventory, index, amount)


def _item_slot(item: dict[str, Any]) -> str:
    raw = _norm(item.get("slot") or item.get("type") or item.get("category") or item.get("name"))
    name = _norm(item.get("name"))
    if any(token in raw or token in name for token in ("bow", "dagger", "sword", "axe", "weapon")):
        return "Weapon"
    if any(token in raw or token in name for token in ("armor", "mail", "leather", "plate")):
        return "Armor"
    if "cloak" in raw or "cloak" in name:
        return "Cloak"
    if "ring" in raw or "band" in name:
        return "Ring"
    return "Utility"


def _equipment(player: dict[str, Any]) -> list[dict[str, Any]]:
    equipment = _safe_list(player.get("equipment"))
    normalized = [item if isinstance(item, dict) else {"name": str(item)} for item in equipment]
    player["equipment"] = normalized
    return normalized


def _equip_item(player: dict[str, Any], item: dict[str, Any]) -> str:
    equipment = _equipment(player)
    slot = _item_slot(item)
    equipped = {"slot": slot, "name": _title(item.get("name") or item.get("label") or item.get("id"))}
    for index, existing in enumerate(equipment):
        if _norm(existing.get("slot")) == _norm(slot):
            equipment[index] = equipped
            return slot
    equipment.append(equipped)
    return slot


def _append_event(state: dict[str, Any], *, title: str, detail: str, kind: str, actor: str = "Player", effects: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    turn = int(state.get("current_turn") or state.get("turn_count") or 0)
    event = {
        "turn": turn,
        "time": state.get("world", {}).get("time") or f"Turn {turn}",
        "title": title,
        "actor": actor,
        "detail": detail,
        "kind": kind,
        "timestamp": _utc_now(),
    }
    if effects:
        event["effects"] = effects
    timeline = _safe_list(state.get("timeline"))
    state["timeline"] = [event, *timeline][:50]
    journal = _safe_dict(state.get("journal"))
    entries = _safe_list(journal.get("entries"))
    journal["entries"] = [event, *entries][:50]
    state["journal"] = journal
    state["summary"] = detail
    state["updated_at"] = event["timestamp"]
    return event


def _mechanics(state: dict[str, Any]) -> dict[str, Any]:
    mechanics = _safe_dict(state.get("mechanics"))
    state["mechanics"] = mechanics
    return mechanics


def _prepend_mechanics_trace(state: dict[str, Any], key: str, trace: dict[str, Any]) -> None:
    mechanics = _mechanics(state)
    traces = _safe_list(mechanics.get(key))
    mechanics[key] = [trace, *traces][:50]


def _record_salvage_trace(state: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    enriched = deepcopy(_safe_dict(trace))
    enriched["turn"] = int(state.get("current_turn") or state.get("turn_count") or 0)
    enriched["timestamp"] = _utc_now()
    _prepend_mechanics_trace(state, "salvage_traces", enriched)
    _prepend_mechanics_trace(state, "item_traces", enriched)
    return enriched


def _record_craft_trace(state: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    enriched = deepcopy(_safe_dict(trace))
    enriched["turn"] = int(state.get("current_turn") or state.get("turn_count") or 0)
    enriched["timestamp"] = _utc_now()
    _prepend_mechanics_trace(state, "crafting_traces", enriched)
    _prepend_mechanics_trace(state, "item_traces", enriched)
    return enriched


def _record_item_use_trace(state: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    enriched = deepcopy(_safe_dict(trace))
    enriched["turn"] = int(state.get("current_turn") or state.get("turn_count") or 0)
    enriched["timestamp"] = _utc_now()
    _prepend_mechanics_trace(state, "item_use_traces", enriched)
    _prepend_mechanics_trace(state, "item_traces", enriched)
    return enriched


def _record_inventory_normalization_trace(state: dict[str, Any], trace: dict[str, Any]) -> None:
    if not trace.get("changed"):
        return
    enriched = {key: deepcopy(value) for key, value in trace.items() if key != "inventory"}
    enriched["turn"] = int(state.get("current_turn") or state.get("turn_count") or 0)
    enriched["timestamp"] = _utc_now()
    _prepend_mechanics_trace(state, "inventory_traces", enriched)
    _prepend_mechanics_trace(state, "item_traces", enriched)


def _session_genre(state: dict[str, Any], session: dict[str, Any]) -> str:
    metadata = _safe_dict(state.get("metadata"))
    identity = _safe_dict(state.get("character_identity"))
    setup = _safe_dict(session.get("setup_payload"))
    return str(metadata.get("genre") or identity.get("genre") or setup.get("genre") or metadata.get("campaign_template") or "classic_fantasy")


def _merge_inventory_stack(inventory: list[dict[str, Any]], stack: dict[str, Any]) -> dict[str, Any]:
    return merge_inventory_stack(inventory, stack)


def _advance_turn(state: dict[str, Any]) -> None:
    state["current_turn"] = int(state.get("current_turn") or 0) + 1
    state["turn_count"] = int(state.get("turn_count") or 0) + 1


def _level_gated_initial_unlocks(tree: dict[str, Any], ability_state: dict[str, Any], hotbar: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Keep legacy backfills progression-based instead of auto-unlocking by level.

    ``build_initial_ability_state`` currently supports demo/high-level packages by
    unlocking every level-eligible active ability. For legacy session backfills,
    loadout actions should preserve the newer progression contract: level gates
    make abilities available, while ability points are still spent to unlock them.
    """
    starting_unlocks = {str(value) for value in _safe_list(tree.get("starting_unlocks"))}
    unlocked = [str(value) for value in _safe_list(ability_state.get("unlocked")) if str(value) in starting_unlocks]
    ranks = {str(key): value for key, value in _safe_dict(ability_state.get("ranks")).items() if str(key) in starting_unlocks}
    filtered_hotbar = {str(slot): str(ability_id) for slot, ability_id in _safe_dict(hotbar).items() if str(ability_id) in starting_unlocks}
    ability_state["unlocked"] = unlocked
    ability_state["ranks"] = ranks
    ability_state["hotbar"] = filtered_hotbar
    return ability_state, filtered_hotbar


def _ensure_ability_progression(state: dict[str, Any], setup_payload: dict[str, Any] | None = None) -> None:
    if state.get("ability_tree") and state.get("ability_state"):
        ensure_world_scale_abilities(state)
        return
    player = _player(state)
    identity = _safe_dict(state.get("character_identity"))
    metadata = _safe_dict(state.get("metadata"))
    setup = _safe_dict(setup_payload)
    setup_player = _safe_dict(setup.get("player"))
    build = str(player.get("build") or "ranger")
    level = int(player.get("level") or 1)
    payload = {
        "campaign_template": metadata.get("campaign_template") or setup.get("campaign_template") or identity.get("genre") or "classic_fantasy",
        "genre": metadata.get("genre") or identity.get("genre") or setup.get("genre") or "classic_fantasy",
        "tone": metadata.get("tone") or identity.get("tone") or setup.get("tone") or "heroic adventure",
        "player": {
            "name": player.get("name") or "Hero",
            "background": player.get("background") or identity.get("background") or setup_player.get("background") or setup.get("background") or "Wanderer",
            "build": build,
        },
        "primary_capability": identity.get("primary_capability") or setup.get("primary_capability"),
        "secondary_capabilities": identity.get("secondary_capabilities") or setup.get("secondary_capabilities") or [],
        "power_source": identity.get("power_source") or setup.get("power_source"),
        "generated_class_name": player.get("class") or identity.get("generated_class_name") or setup.get("generated_class_name"),
        "generated_class_summary": identity.get("generated_class_summary") or setup.get("generated_class_summary"),
    }
    progression = build_progression_package(payload, build_id=build, level=level, seed=metadata.get("seed") if isinstance(metadata.get("seed"), int) else None)
    tree = _safe_dict(progression.get("ability_tree"))
    ability_state, hotbar = _level_gated_initial_unlocks(tree, _safe_dict(progression.get("ability_state")), _safe_dict(progression.get("hotbar")))
    state.setdefault("character_identity", progression["character_identity"])
    state["ability_tree"] = tree
    state["ability_state"] = ability_state
    state["hotbar"] = hotbar
    ensure_world_scale_abilities(state)


def _use_item(state: dict[str, Any], player: dict[str, Any], inventory: list[dict[str, Any]], index: int, item: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    result = use_inventory_item(state, player, inventory, index, item)
    return str(result.get("name") or _title(item.get("name") or item.get("label") or item.get("id")) or "item"), str(result.get("detail") or ""), result


def _requested_ability_id(request: RpgLoadoutActionRequest) -> str | None:
    return request.ability_id or request.ability_name


def _requested_recipe_id(request: RpgLoadoutActionRequest) -> str | None:
    return request.recipe_id or request.recipe_name or request.item_name


def apply_loadout_action(session_id: str, request: RpgLoadoutActionRequest) -> dict[str, Any]:
    session = load_session(session_id)
    if not session:
        return {"ok": False, "error": "session_not_found", "session_id": session_id}

    updated = deepcopy(session)
    state = _state(updated)
    player = _player(state)
    _record_inventory_normalization_trace(state, normalize_player_inventory(player))
    action = request.action
    extra_response: dict[str, Any] = {}
    event_effects: list[dict[str, Any]] | None = None

    if action == "craft":
        inventory = _inventory(player)
        craft_result = craft_from_inventory(inventory, _requested_recipe_id(request), station=request.station)
        if not craft_result.get("ok"):
            return {
                "ok": False,
                "error": craft_result.get("error") or "craft_failed",
                "session_id": session_id,
                "recipe_id": craft_result.get("recipe_id") or _requested_recipe_id(request),
                "detail": craft_result.get("detail"),
                "missing": craft_result.get("missing", []),
                "required_station": craft_result.get("required_station"),
                "station": craft_result.get("station") or request.station,
            }
        _advance_turn(state)
        trace = _record_craft_trace(state, _safe_dict(craft_result.get("trace")))
        output = _safe_dict(craft_result.get("output"))
        output_name = _title(output.get("name") or output.get("id") or output.get("item_id")) or "item"
        detail = str(craft_result.get("detail") or f"Crafted {output_name}.")
        title = f"Crafted {output_name}"
        event_effects = [
            {"action": "consume", "items": _safe_list(craft_result.get("consumed_items"))},
            {"action": "add_item", "output": output},
        ]
        event = _append_event(state, title=title, detail=detail, kind="craft", effects=event_effects)
        extra_response = {
            "recipe_id": craft_result.get("recipe_id"),
            "recipe_name": craft_result.get("recipe_name"),
            "output": output,
            "consumed_items": _safe_list(craft_result.get("consumed_items")),
            "mechanics_trace": trace,
        }
    elif action in {"inspect", "use", "equip", "drop", "salvage"}:
        inventory, index, item = _find_item(player, request.item_name)
        if item is None or index < 0:
            return {"ok": False, "error": "item_not_found", "session_id": session_id, "item_name": request.item_name}
        name = _title(item.get("name") or item.get("label") or item.get("id")) or "item"
        if action == "inspect":
            detail = f"You inspect {name}. It is carried in inventory and can be used, equipped, or dropped if the situation allows."
            title = f"Inspected {name}"
            kind = "inspect"
        elif action == "use":
            name, detail, use_result = _use_item(state, player, inventory, index, item)
            title = f"Used {name}"
            kind = "item"
            _advance_turn(state)
            trace = _record_item_use_trace(state, _safe_dict(use_result.get("trace")))
            event_effects = _safe_list(use_result.get("effects"))
            extra_response = {
                "effects": event_effects,
                "consumed": bool(use_result.get("consumed")),
                "repairs": _safe_list(use_result.get("repairs")),
                "mechanics_trace": trace,
            }
        elif action == "equip":
            slot = _equip_item(player, item)
            detail = f"You equipped {name} in the {slot} slot."
            title = f"Equipped {name}"
            kind = "equipment"
            _advance_turn(state)
        elif action == "salvage":
            salvage_result = salvage_item(item, genre=_session_genre(state, updated))
            if not salvage_result.ok:
                return {
                    "ok": False,
                    "error": salvage_result.error or "salvage_failed",
                    "session_id": session_id,
                    "item_name": name,
                    "detail": salvage_result.detail,
                }
            _consume(inventory, index)
            for output in salvage_result.outputs:
                _merge_inventory_stack(inventory, output)
            _advance_turn(state)
            trace = _record_salvage_trace(state, salvage_result.trace)
            detail = salvage_result.detail
            title = f"Salvaged {name}"
            kind = "salvage"
            event_effects = [
                {"action": "consume", "items": salvage_result.consumed_items},
                {"action": "add_materials", "outputs": salvage_result.outputs},
            ]
            extra_response = {
                "outputs": salvage_result.outputs,
                "consumed_items": salvage_result.consumed_items,
                "repairs": salvage_result.repairs,
                "mechanics_trace": trace,
            }
        else:
            if is_protected_item(item):
                return {"ok": False, "error": "protected_item", "session_id": session_id, "item_name": name}
            _consume(inventory, index)
            detail = f"You dropped one {name}."
            title = f"Dropped {name}"
            kind = "inventory"
            _advance_turn(state)
        event = _append_event(state, title=title, detail=detail, kind=kind, effects=event_effects)
    elif action in {"use_ability", "hotbar"}:
        _ensure_ability_progression(state, _safe_dict(updated.get("setup_payload")))
        requested_ability = request.ability_name or request.ability_id
        world_result = apply_world_scale_loadout_ability(state, ability_name=requested_ability, hotbar_slot=request.hotbar_slot, target=request.target or "the wider world")
        if world_result.get("handled"):
            if not world_result.get("ok"):
                return {"ok": False, "error": world_result.get("error") or "world_ability_failed", "session_id": session_id, "detail": world_result.get("detail"), "ability_id": world_result.get("ability_id"), "effects": world_result.get("effects", [])}
            _advance_turn(state)
            event = _append_event(state, title=f"Used {world_result.get('name')}", detail=str(world_result.get("detail") or "World state changed."), kind="world_ability", effects=_safe_list(world_result.get("effects")))
        else:
            result = apply_ability_to_state(state, ability_name=requested_ability, hotbar_slot=request.hotbar_slot, target=request.target or "the current situation")
            if not result.ok:
                return {"ok": False, "error": result.error or "ability_failed", "session_id": session_id, "detail": result.detail, "ability_id": result.ability_id}
            _advance_turn(state)
            event = _append_event(state, title=f"Used {result.name}", detail=result.detail, kind="ability", effects=result.effects)
    elif action in {"unlock_ability", "upgrade_ability", "assign_hotbar", "remove_hotbar"}:
        _ensure_ability_progression(state, _safe_dict(updated.get("setup_payload")))
        ability_id = _requested_ability_id(request)
        if action == "unlock_ability":
            result = unlock_ability_in_state(state, str(ability_id or ""))
        elif action == "upgrade_ability":
            result = upgrade_ability_rank_in_state(state, str(ability_id or ""))
        elif action == "assign_hotbar":
            result = assign_ability_to_hotbar(state, str(ability_id or ""), request.hotbar_slot or "1")
        else:
            result = remove_hotbar_slot(state, request.hotbar_slot or "1")
        if not result.ok:
            return {"ok": False, "error": result.error or "ability_progression_failed", "session_id": session_id, "detail": result.detail, "ability_id": result.ability_id, "slot": result.slot}
        event = _append_event(
            state,
            title="Updated ability progression",
            detail=result.detail,
            kind="ability_progression",
            effects=[{"action": action, "ability_id": result.ability_id, "slot": result.slot}],
        )
    else:
        return {"ok": False, "error": "unsupported_loadout_action", "session_id": session_id, "action": action}

    manifest = _safe_dict(updated.get("manifest"))
    manifest["updated_at"] = state.get("updated_at") or _utc_now()
    manifest["turn_count"] = state.get("turn_count")
    manifest["current_turn"] = state.get("current_turn")
    updated["manifest"] = manifest

    write_ability_coverage_snapshot(state)
    saved = save_session(updated, compact=False)
    return {"ok": True, "session_id": session_id, "status": "ready", "event": event, "session": saved, "game": saved.get("state", {}), **extra_response}
