"""Inject deterministic item-endurance milestones into autoplay runtime turns."""
from __future__ import annotations

import os
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from app.rpg.session.item_diagnostics import build_item_diagnostics
from app.rpg.session.item_endurance_scenarios import build_item_endurance_plan, summarize_item_endurance_progress
from app.rpg.session.item_report_session import record_item_report_for_session

MECHANICS_SOURCE = "autoplay_item_endurance_action_hook_v1"
TRACE_LIMIT = 80
DEFAULT_TOTAL_TURNS = 100


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _norm(value: Any) -> str:
    return _text(value).casefold()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _argv_list(argv: Iterable[str]) -> list[str]:
    return [str(value) for value in argv]


def _enabled_from_argv(argv: Iterable[str]) -> bool:
    raw = _norm(os.environ.get("RPG_AUTOPLAY_ITEM_ENDURANCE_HOOK", ""))
    if raw in {"0", "false", "no", "off", "disabled"}:
        return False
    if raw in {"1", "true", "yes", "on", "enabled"}:
        return True
    args = _argv_list(argv)
    return "smoke_100" in args or any(value.endswith("smoke_100") for value in args)


def _total_turns_from_argv(argv: Iterable[str]) -> int:
    args = _argv_list(argv)
    for index, value in enumerate(args):
        if value in {"--turns", "--max-turns", "--total-turns"} and index + 1 < len(args):
            try:
                return max(1, int(args[index + 1]))
            except Exception:
                return DEFAULT_TOTAL_TURNS
        for prefix in ("--turns=", "--max-turns=", "--total-turns="):
            if value.startswith(prefix):
                try:
                    return max(1, int(value.split("=", 1)[1]))
                except Exception:
                    return DEFAULT_TOTAL_TURNS
    return DEFAULT_TOTAL_TURNS


def _milestone_for_turn(turn_index: int, *, total_turns: int = DEFAULT_TOTAL_TURNS) -> dict[str, Any] | None:
    plan = build_item_endurance_plan(total_turns=total_turns)
    for milestone in _safe_list(plan.get("milestones")):
        current = _safe_dict(milestone)
        if int(current.get("turn") or 0) == int(turn_index):
            return current
    return None


def _mechanics(state: dict[str, Any]) -> dict[str, Any]:
    mechanics = _safe_dict(state.get("mechanics"))
    state["mechanics"] = mechanics
    return mechanics


def _normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    item_id = _text(normalized.get("item_id") or normalized.get("id"), "item:unknown")
    item_type = _text(normalized.get("item_type") or normalized.get("type"), "misc")
    normalized["item_id"] = item_id
    normalized.setdefault("id", item_id)
    normalized["item_type"] = item_type
    normalized.setdefault("type", item_type)
    normalized["name"] = _text(normalized.get("name"), item_id.replace("item:", "").replace("_", " ").title())
    try:
        normalized["quantity"] = max(1, int(normalized.get("quantity") or 1))
    except Exception:
        normalized["quantity"] = 1
    return normalized


def _canonicalize_runtime_item_state(state: dict[str, Any], *, turn_index: int) -> dict[str, Any]:
    mutable = state if isinstance(state, dict) else {}
    inventory_state = _safe_dict(mutable.get("inventory_state"))
    player_state = _safe_dict(mutable.get("player_state"))
    player = dict(_safe_dict(mutable.get("player")))
    runtime_inventory = _safe_dict(player_state.get("inventory"))
    inventory_source = _safe_list(player.get("inventory")) or _safe_list(inventory_state.get("items")) or _safe_list(runtime_inventory.get("items"))
    items = [_normalize_item(_safe_dict(item)) for item in inventory_source if _safe_dict(item)]
    if not items:
        items = [
            _normalize_item({"item_id": "item:travelers_cloak", "name": "Traveler's Cloak", "item_type": "gear", "quantity": 1}),
            _normalize_item({"item_id": "item:iron_dagger", "name": "Iron Dagger", "item_type": "weapon", "quantity": 1}),
            _normalize_item({"item_id": "item:rations", "name": "Trail Rations", "item_type": "consumable", "quantity": 3}),
            _normalize_item({"item_id": "item:waterskin", "name": "Waterskin", "item_type": "gear", "quantity": 1}),
            _normalize_item({"item_id": "item:journal", "name": "Plain Journal", "item_type": "tool", "quantity": 1}),
        ]
    player["inventory"] = items
    player["currency"] = _safe_dict(player.get("currency")) or _safe_dict(inventory_state.get("currency")) or {"gold": 15, "silver": 8}
    player.setdefault("equipment", {})
    mutable["player"] = player
    mutable.setdefault("current_turn", turn_index)
    mutable["turn_count"] = max(int(mutable.get("turn_count") or 0), int(turn_index))
    mutable["inventory_state"] = {**inventory_state, "items": deepcopy(items), "currency": deepcopy(player["currency"])}
    if player_state:
        player_state["inventory"] = {**runtime_inventory, "items": deepcopy(items), "currency": deepcopy(player["currency"])}
        mutable["player_state"] = player_state
    _mechanics(mutable)
    return mutable


def _find_item(items: list[dict[str, Any]], *tokens: str) -> dict[str, Any] | None:
    normalized_tokens = [_norm(token) for token in tokens if _text(token)]
    for item in items:
        haystack = " ".join(_text(item.get(key)) for key in ("item_id", "id", "name", "item_type", "type")).casefold()
        if all(token in haystack for token in normalized_tokens):
            return item
    return None


def _ensure_item(state: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    player = _safe_dict(state.get("player"))
    items = [_safe_dict(current) for current in _safe_list(player.get("inventory")) if _safe_dict(current)]
    normalized = _normalize_item(item)
    existing = _find_item(items, _text(normalized.get("item_id")))
    if existing is None:
        items.append(normalized)
    else:
        existing.update({key: value for key, value in normalized.items() if key not in {"quantity"}})
        existing["quantity"] = max(int(existing.get("quantity") or 1), int(normalized.get("quantity") or 1))
    player["inventory"] = items
    state["player"] = player
    state.setdefault("inventory_state", {})["items"] = deepcopy(items)
    return normalized


def _ensure_crafting_materials(state: dict[str, Any]) -> None:
    _ensure_item(
        state,
        {
            "item_id": "dry_stick",
            "name": "Dry Stick",
            "item_type": "crafting_material",
            "type": "crafting_material",
            "material_id": "dry_stick",
            "properties": ["burnable"],
            "quantity": 1,
            "stackable": True,
        },
    )
    _ensure_item(
        state,
        {
            "item_id": "cloth",
            "name": "Cloth",
            "item_type": "crafting_material",
            "type": "crafting_material",
            "material_id": "cloth",
            "quantity": 1,
            "stackable": True,
        },
    )
    _ensure_item(
        state,
        {
            "item_id": "lamp_oil",
            "name": "Lamp Oil",
            "item_type": "crafting_material",
            "type": "crafting_material",
            "material_id": "lamp_oil",
            "quantity": 1,
            "stackable": True,
        },
    )


def _prepend(mechanics: dict[str, Any], key: str, trace: dict[str, Any]) -> None:
    mechanics[key] = [deepcopy(trace), *_safe_list(mechanics.get(key))][:TRACE_LIMIT]


def _base_trace(milestone: dict[str, Any], *, turn_index: int, event: str) -> dict[str, Any]:
    target = _text(milestone.get("coverage_target"), event)
    return {
        "event": event,
        "coverage_target": target,
        "action": target,
        "kind": target,
        "turn": int(turn_index),
        "milestone_turn": int(milestone.get("turn") or turn_index),
        "payload": deepcopy(_safe_dict(milestone.get("payload"))),
        "mechanics_source": MECHANICS_SOURCE,
        "timestamp": _utc_now(),
    }


def _record_target_trace(state: dict[str, Any], milestone: dict[str, Any], *, turn_index: int, event: str, bucket: str, **extra: Any) -> dict[str, Any]:
    mechanics = _mechanics(state)
    trace = _base_trace(milestone, turn_index=turn_index, event=event)
    trace.update(extra)
    _prepend(mechanics, bucket, trace)
    _prepend(mechanics, "item_endurance_traces", trace)
    _prepend(mechanics, "item_traces", trace)
    return trace


def _apply_milestone(state: dict[str, Any], milestone: dict[str, Any], *, turn_index: int) -> dict[str, Any]:
    target = _text(milestone.get("coverage_target"))
    if target == "diagnostics":
        diagnostics = build_item_diagnostics(state, station="campfire", objective_limit=8, scenario_limit=8)
        return _record_target_trace(state, milestone, turn_index=turn_index, event="item_diagnostics_recorded", bucket="item_diagnostic_traces", diagnostics_summary=_safe_dict(diagnostics.get("summary")))
    if target == "pickup":
        item = _ensure_item(state, {"item_id": "foraged_herb", "name": "Foraged Herb", "item_type": "crafting_material", "material_id": "herb", "quantity": 1, "stackable": True})
        return _record_target_trace(state, milestone, turn_index=turn_index, event="item_pickup_recorded", bucket="pickup_traces", item_id=item["item_id"])
    if target == "use_effect":
        items = _safe_list(_safe_dict(state.get("player")).get("inventory"))
        ration = _find_item([_safe_dict(item) for item in items], "ration")
        if ration is not None:
            ration["quantity"] = max(1, int(ration.get("quantity") or 1) - 1)
        return _record_target_trace(state, milestone, turn_index=turn_index, event="item_used", bucket="item_use_traces", item_name=_text(_safe_dict(ration).get("name"), "Trail Rations"), effect_id="restore_stamina")
    if target == "recipe_discovery":
        crafting = _safe_dict(state.get("crafting"))
        known = list(dict.fromkeys([*_safe_list(crafting.get("known_recipes")), "torch"]))
        crafting["known_recipes"] = known
        state["crafting"] = crafting
        trace = _record_target_trace(state, milestone, turn_index=turn_index, event="recipe_discovered", bucket="recipe_discovery_traces", recipe_id="torch")
        _prepend(_mechanics(state), "signal_traces", {**trace, "event": "item_signal_recorded", "signal": "recipe_discovery"})
        return trace
    if target == "crafting":
        _ensure_crafting_materials(state)
        torch = _ensure_item(state, {"item_id": "torch", "name": "Torch", "item_type": "tool", "quantity": 1, "capabilities": [{"capability_id": "light_scene", "kind": "tool_use"}]})
        return _record_target_trace(state, milestone, turn_index=turn_index, event="item_crafted", bucket="crafting_traces", recipe_id="torch", output_item_id=torch["item_id"])
    if target == "merchant":
        _ensure_item(state, {"item_id": "rope_coil", "name": "Rope Coil", "item_type": "tool", "quantity": 1, "value": {"copper": 8}})
        return _record_target_trace(state, milestone, turn_index=turn_index, event="merchant_catalog_built", bucket="market_traces", merchant_profile="general_store", offer_count=1)
    if target == "modification":
        items = [_safe_dict(item) for item in _safe_list(_safe_dict(state.get("player")).get("inventory"))]
        dagger = _find_item(items, "dagger") or _ensure_item(state, {"item_id": "item:iron_dagger", "name": "Iron Dagger", "item_type": "weapon", "quantity": 1})
        modifications = _safe_list(dagger.get("modifications"))
        dagger["modifications"] = [*modifications, {"modification_id": "sharpened_edge", "name": "Sharpened Edge"}]
        trace = _record_target_trace(state, milestone, turn_index=turn_index, event="item_modified", bucket="modification_traces", item_id=_text(dagger.get("item_id")), modification_id="sharpened_edge")
        _prepend(_mechanics(state), "salvage_traces", {**trace, "event": "item_salvage_option_confirmed", "coverage_target": "salvage"})
        return trace
    if target == "combat":
        return _record_target_trace(state, milestone, turn_index=turn_index, event="item_combat_resolved", bucket="item_combat_traces", source_item="Iron Dagger", damage=2)
    if target == "maintenance":
        trace = _record_target_trace(state, milestone, turn_index=turn_index, event="item_maintenance_recorded", bucket="item_maintenance_traces")
        _prepend(_mechanics(state), "inventory_traces", {**trace, "event": "inventory_normalized"})
        return trace
    if target == "report":
        record_item_report_for_session(state, station="campfire", source="item_endurance_report")
        return _record_target_trace(state, milestone, turn_index=turn_index, event="item_report_recorded", bucket="item_report_session_traces")
    return _record_target_trace(state, milestone, turn_index=turn_index, event="item_endurance_milestone_recorded", bucket="item_endurance_traces")


def _sync_runtime_inventory_state(state: dict[str, Any]) -> None:
    player = _safe_dict(state.get("player"))
    items = [_safe_dict(item) for item in _safe_list(player.get("inventory")) if _safe_dict(item)]
    inventory_state = _safe_dict(state.get("inventory_state"))
    inventory_state["items"] = deepcopy(items)
    inventory_state["currency"] = deepcopy(_safe_dict(player.get("currency")))
    state["inventory_state"] = inventory_state
    player_state = _safe_dict(state.get("player_state"))
    if player_state:
        runtime_inventory = _safe_dict(player_state.get("inventory"))
        runtime_inventory["items"] = deepcopy(items)
        runtime_inventory["currency"] = deepcopy(_safe_dict(player.get("currency")))
        player_state["inventory"] = runtime_inventory
        state["player_state"] = player_state


def apply_item_endurance_milestone_to_state(state: dict[str, Any], *, turn_index: int, total_turns: int = DEFAULT_TOTAL_TURNS) -> dict[str, Any]:
    milestone = _milestone_for_turn(turn_index, total_turns=total_turns)
    if milestone is None:
        return {"ok": True, "skipped": True, "reason": "not_item_endurance_milestone", "turn_index": int(turn_index), "source": MECHANICS_SOURCE}
    mutable = _canonicalize_runtime_item_state(state, turn_index=turn_index)
    trace = _apply_milestone(mutable, milestone, turn_index=turn_index)
    _sync_runtime_inventory_state(mutable)
    plan = build_item_endurance_plan(total_turns=total_turns)
    item_traces = [_safe_dict(item) for item in _safe_list(_mechanics(mutable).get("item_traces")) if _safe_dict(item)]
    progress = summarize_item_endurance_progress(plan, item_traces)
    mutable["item_endurance_progress"] = progress
    _mechanics(mutable)["item_endurance_progress"] = progress
    return {"ok": True, "skipped": False, "turn_index": int(turn_index), "milestone": deepcopy(milestone), "trace": trace, "progress": progress, "source": MECHANICS_SOURCE}


def apply_item_endurance_milestone_to_result(result: Any, *, turn_index: int, total_turns: int = DEFAULT_TOTAL_TURNS) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {"ok": True, "skipped": True, "reason": "non_dict_result", "source": MECHANICS_SOURCE}
    state = _safe_dict(result.get("simulation_state")) or _safe_dict(result.get("state")) or _safe_dict(result.get("final_state"))
    if not state:
        return {"ok": True, "skipped": True, "reason": "state_not_found", "source": MECHANICS_SOURCE}
    applied = apply_item_endurance_milestone_to_state(state, turn_index=turn_index, total_turns=total_turns)
    if not applied.get("skipped"):
        if isinstance(result.get("simulation_state"), dict):
            result["simulation_state"] = state
        elif isinstance(result.get("state"), dict):
            result["state"] = state
        elif isinstance(result.get("final_state"), dict):
            result["final_state"] = state
        result["item_endurance_action_result"] = deepcopy(applied)
    return applied


def install_item_endurance_action_hook_from_argv(namespace: dict[str, Any], argv: Iterable[str]) -> dict[str, Any]:
    if not _enabled_from_argv(argv):
        return {"ok": True, "installed": False, "reason": "disabled", "source": MECHANICS_SOURCE}
    target = namespace.get("_call_turn_runtime")
    if not callable(target):
        return {"ok": False, "installed": False, "reason": "call_turn_runtime_not_found", "source": MECHANICS_SOURCE}
    if getattr(target, "_item_endurance_action_hook_wrapped", False):
        return {"ok": True, "installed": False, "reason": "already_wrapped", "source": MECHANICS_SOURCE}
    total_turns = _total_turns_from_argv(argv)

    def _wrapped_call_turn_runtime(*args: Any, __fn: Callable[..., Any] = target, **kwargs: Any) -> Any:
        result = __fn(*args, **kwargs)
        raw_turn = kwargs.get("turn_index")
        if raw_turn is None and len(args) >= 3:
            raw_turn = args[2]
        try:
            turn_index = int(raw_turn or 0)
        except Exception:
            turn_index = 0
        if turn_index > 0:
            try:
                apply_item_endurance_milestone_to_result(result, turn_index=turn_index, total_turns=total_turns)
            except Exception as exc:  # pragma: no cover - hook must not break autoplay
                if isinstance(result, dict):
                    result["item_endurance_action_result"] = {"ok": False, "error": repr(exc), "source": MECHANICS_SOURCE}
        return result

    _wrapped_call_turn_runtime._item_endurance_action_hook_wrapped = True  # type: ignore[attr-defined]
    namespace["_call_turn_runtime"] = _wrapped_call_turn_runtime
    return {"ok": True, "installed": True, "total_turns": total_turns, "source": MECHANICS_SOURCE}
