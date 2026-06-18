"""Deterministic inventory, equipment, and ability actions for RPG sessions."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel

from app.rpg.session.ability_system import (
    apply_ability_to_state,
    assign_ability_to_hotbar,
    build_progression_package,
    remove_hotbar_slot,
    unlock_ability_in_state,
    upgrade_ability_rank_in_state,
)
from app.rpg.session.service import load_session, save_session

LoadoutActionKind = Literal[
    "inspect",
    "use",
    "equip",
    "drop",
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


def _advance_turn(state: dict[str, Any]) -> None:
    state["current_turn"] = int(state.get("current_turn") or 0) + 1
    state["turn_count"] = int(state.get("turn_count") or 0) + 1


def _ensure_ability_progression(state: dict[str, Any], setup_payload: dict[str, Any] | None = None) -> None:
    if state.get("ability_tree") and state.get("ability_state"):
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
    state.setdefault("character_identity", progression["character_identity"])
    state["ability_tree"] = progression["ability_tree"]
    state["ability_state"] = progression["ability_state"]
    state["hotbar"] = progression["hotbar"]


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
        scene_state = _safe_dict(state.get("scene_state"))
        statuses = _safe_list(scene_state.get("statuses"))
        statuses.insert(0, {"status": "lit_torch", "dimension": "environment", "source": name, "created_at": _utc_now()})
        scene_state["statuses"] = statuses[:20]
        state["scene_state"] = scene_state
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
        affordances = _safe_dict(state.get("narrative_affordances"))
        dialogue = _safe_list(affordances.get("dialogue"))
        dialogue.insert(0, {"tag": "ask_about_written_clue", "source": name, "dimension": "narrative", "created_at": _utc_now()})
        affordances["dialogue"] = dialogue[:20]
        state["narrative_affordances"] = affordances
        detail = f"You reviewed {name} for useful clues."
    else:
        consumed = False
        detail = f"You used {name}, but it has no special deterministic effect yet."

    if consumed:
        _consume(inventory, index)
    return name, detail


def _requested_ability_id(request: RpgLoadoutActionRequest) -> str | None:
    return request.ability_id or request.ability_name


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
        _ensure_ability_progression(state, _safe_dict(updated.get("setup_payload")))
        result = apply_ability_to_state(state, ability_id=request.ability_id, ability_name=request.ability_name, hotbar_slot=request.hotbar_slot, target=request.target or "the current situation")
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

    saved = save_session(updated, compact=False)
    return {"ok": True, "session_id": session_id, "status": "ready", "event": event, "session": saved, "game": saved.get("state", {})}
