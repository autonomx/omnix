"""Deterministic inventory, equipment, and ability actions for RPG sessions."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.rpg.session.service import load_session, save_session

LoadoutActionKind = Literal["inspect", "use", "equip", "drop", "use_ability", "hotbar"]


class RpgLoadoutActionRequest(BaseModel):
    action: LoadoutActionKind
    item_name: str | None = None
    ability_name: str | None = None
    hotbar_slot: str | int | None = None
    target: str | None = None


ABILITY_CATALOG: dict[str, dict[str, Any]] = {
    "aimed shot": {"name": "Aimed Shot", "slot": "1", "icon": "✦", "resource": "stamina", "cost": 10, "summary": "A careful ranged attack prepared against the best visible target."},
    "frost arrow": {"name": "Frost Arrow", "slot": "2", "icon": "↯", "resource": "mana", "cost": 12, "summary": "A freezing arrow readied to slow or punish a dangerous foe."},
    "camouflage": {"name": "Camouflage", "slot": "3", "icon": "☘", "resource": "stamina", "cost": 8, "summary": "The hero blends into terrain and gains a stealth advantage."},
    "radiant flare": {"name": "Radiant Flare", "slot": "4", "icon": "✹", "resource": "mana", "cost": 15, "summary": "A burst of light reveals threats and can stagger nearby enemies."},
    "volley": {"name": "Volley", "slot": "5", "icon": "⟡", "resource": "stamina", "cost": 15, "summary": "A quick spread of shots pressures clustered enemies."},
    "dash": {"name": "Dash", "slot": "6", "icon": "⇥", "resource": "stamina", "cost": 12, "summary": "A fast reposition that improves immediate tactical options."},
}

HOTBAR_BY_SLOT = {str(value["slot"]): value for value in ABILITY_CATALOG.values()}


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
    inventory = _safe_list(player.get("inventory"))
    normalized: list[dict[str, Any]] = []
    for item in inventory:
        if isinstance(item, dict):
            normalized.append(item)
        else:
            normalized.append({"name": str(item), "quantity": 1})
    player["inventory"] = normalized
    return normalized


def _find_item(player: dict[str, Any], item_name: str | None) -> tuple[list[dict[str, Any]], int, dict[str, Any] | None]:
    inventory = _inventory(player)
    wanted = _norm(item_name)
    if not wanted:
        return inventory, -1, None
    for index, item in enumerate(inventory):
        names = [item.get("name"), item.get("label"), item.get("id")]
        if any(_norm(name) == wanted for name in names):
            return inventory, index, item
    for index, item in enumerate(inventory):
        if wanted in _norm(item.get("name") or item.get("label") or item.get("id")):
            return inventory, index, item
    return inventory, -1, None


def _quantity(item: dict[str, Any]) -> int:
    for key in ("quantity", "count", "qty", "amount"):
        value = item.get(key)
        if isinstance(value, (int, float)):
            return max(0, int(value))
    return 1


def _set_quantity(inventory: list[dict[str, Any]], index: int, quantity: int) -> None:
    if quantity <= 0:
        inventory.pop(index)
        return
    inventory[index]["quantity"] = quantity


def _consume(inventory: list[dict[str, Any]], index: int, amount: int = 1) -> None:
    _set_quantity(inventory, index, _quantity(inventory[index]) - amount)


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


def _append_event(state: dict[str, Any], *, title: str, detail: str, kind: str, actor: str = "Player") -> dict[str, Any]:
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
    timeline = _safe_list(state.get("timeline"))
    state["timeline"] = [event, *timeline][:50]
    journal = _safe_dict(state.get("journal"))
    entries = _safe_list(journal.get("entries"))
    journal["entries"] = [event, *entries][:50]
    state["journal"] = journal
    state["summary"] = detail
    state["updated_at"] = event["timestamp"]
    return event


def _advance_turn(state: dict[str, Any]) -> None:
    state["current_turn"] = int(state.get("current_turn") or 0) + 1
    state["turn_count"] = int(state.get("turn_count") or 0) + 1


def _use_item(state: dict[str, Any], player: dict[str, Any], inventory: list[dict[str, Any]], index: int, item: dict[str, Any]) -> tuple[str, str]:
    name = _title(item.get("name") or item.get("label") or item.get("id")) or "item"
    lower = _norm(name)
    consumed = True

    if "health" in lower or "healing" in lower:
        current, maximum = _change_metric(player, "hp", 25)
        detail = f"You used {name} and recovered HP to {current}/{maximum}."
    elif "mana" in lower or "tonic" in lower:
        current, maximum = _change_metric(player, "mana", 25)
        detail = f"You used {name} and restored mana to {current}/{maximum}."
    elif "ration" in lower or "food" in lower:
        current, maximum = _change_metric(player, "stamina", 10)
        detail = f"You ate {name} and recovered stamina to {current}/{maximum}."
    elif "torch" in lower:
        runtime = _safe_dict(state.get("runtime"))
        runtime["light_source"] = "torch"
        state["runtime"] = runtime
        detail = f"You lit {name}. The immediate area is easier to inspect."
    elif "focus" in lower or "crystal" in lower:
        current, maximum = _change_metric(player, "mana", 10)
        detail = f"You focused through {name}, steadying your magic and mana to {current}/{maximum}."
    elif "cloak" in lower or "armor" in lower or "bow" in lower or "dagger" in lower or "ring" in lower or "band" in lower:
        slot = _equip_item(player, item)
        consumed = False
        detail = f"You equipped {name} in the {slot} slot."
    elif "journal" in lower or "scroll" in lower:
        consumed = False
        detail = f"You reviewed {name} for useful clues."
    else:
        consumed = False
        detail = f"You used {name}, but it has no special deterministic effect yet."

    if consumed:
        _consume(inventory, index)
    return name, detail


def _ability_from_request(request: RpgLoadoutActionRequest) -> dict[str, Any] | None:
    if request.hotbar_slot is not None:
        ability = HOTBAR_BY_SLOT.get(str(request.hotbar_slot))
        if ability:
            return ability
    wanted = _norm(request.ability_name)
    if wanted:
        return ABILITY_CATALOG.get(wanted) or next((ability for key, ability in ABILITY_CATALOG.items() if wanted in key), None)
    return None


def _use_ability(state: dict[str, Any], player: dict[str, Any], request: RpgLoadoutActionRequest) -> tuple[bool, str, str]:
    ability = _ability_from_request(request)
    if not ability:
        return False, "unknown_ability", "Ability was not found in the deterministic catalog."

    resource_name = str(ability["resource"])
    cost = int(ability["cost"])
    metric = _metric(player, resource_name)
    current = int(metric.get("current") or 0)
    maximum = int(metric.get("max") or current)
    name = str(ability["name"])
    if current < cost:
        return False, "insufficient_resource", f"{name} requires {cost} {resource_name}, but only {current}/{maximum} is available."

    metric["current"] = current - cost
    target = request.target or "the best available target"
    runtime = _safe_dict(state.get("runtime"))
    buffs = _safe_list(runtime.get("effects"))
    buffs.insert(0, {"source": name, "target": target, "created_at": _utc_now()})
    runtime["effects"] = buffs[:12]
    state["runtime"] = runtime
    detail = f"You used {name} on {target}. {ability['summary']} {resource_name.title()} is now {metric['current']}/{maximum}."
    return True, name, detail


def apply_loadout_action(session_id: str, request: RpgLoadoutActionRequest) -> dict[str, Any]:
    session = load_session(session_id)
    if not session:
        return {"ok": False, "error": "session_not_found", "session_id": session_id}

    updated = deepcopy(session)
    state = _state(updated)
    player = _player(state)
    action = request.action

    if action in {"inspect", "use", "equip", "drop"}:
        inventory, index, item = _find_item(player, request.item_name)
        if item is None or index < 0:
            return {"ok": False, "error": "item_not_found", "session_id": session_id, "item_name": request.item_name}

        name = _title(item.get("name") or item.get("label") or item.get("id")) or "item"
        if action == "inspect":
            detail = f"You inspect {name}. It is carried in inventory and can be used, equipped, or dropped if the situation allows."
            title = f"Inspected {name}"
            kind = "inspect"
        elif action == "use":
            name, detail = _use_item(state, player, inventory, index, item)
            title = f"Used {name}"
            kind = "item"
            _advance_turn(state)
        elif action == "equip":
            slot = _equip_item(player, item)
            detail = f"You equipped {name} in the {slot} slot."
            title = f"Equipped {name}"
            kind = "equipment"
            _advance_turn(state)
        else:
            if _norm(name) in {"journal"}:
                return {"ok": False, "error": "protected_item", "session_id": session_id, "item_name": name}
            _consume(inventory, index)
            detail = f"You dropped one {name}."
            title = f"Dropped {name}"
            kind = "inventory"
            _advance_turn(state)

        event = _append_event(state, title=title, detail=detail, kind=kind)
    elif action in {"use_ability", "hotbar"}:
        ok, name, detail = _use_ability(state, player, request)
        if not ok:
            return {"ok": False, "error": name, "session_id": session_id, "detail": detail}
        _advance_turn(state)
        event = _append_event(state, title=f"Used {name}", detail=detail, kind="ability")
    else:
        return {"ok": False, "error": "unsupported_loadout_action", "session_id": session_id, "action": action}

    manifest = _safe_dict(updated.get("manifest"))
    manifest["updated_at"] = state.get("updated_at") or _utc_now()
    manifest["turn_count"] = state.get("turn_count")
    manifest["current_turn"] = state.get("current_turn")
    updated["manifest"] = manifest

    saved = save_session(updated, compact=False)
    return {
        "ok": True,
        "session_id": session_id,
        "status": "ready",
        "event": event,
        "session": saved,
        "game": saved.get("state", {}),
    }
