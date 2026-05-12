from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from app.rpg.mechanics.mechanics_opportunities import match_mechanic_opportunity


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return str(value or "")


def _currency(state: Mapping[str, Any]) -> Dict[str, int]:
    raw = _safe_dict(state.get("currency"))
    # Starter fallback for autoplay seed if no economy init has happened.
    if not raw:
        return {"gold": 1, "silver": 20, "copper": 50}
    return {str(k): int(v or 0) for k, v in raw.items()}


def _flags(state: Mapping[str, Any]) -> Dict[str, bool]:
    raw = state.get("flags") or state.get("world_flags") or {}
    if isinstance(raw, dict):
        return {str(k): bool(v) for k, v in raw.items()}
    if isinstance(raw, list):
        return {str(v): True for v in raw}
    return {}


def _apply_currency_delta(currency: Dict[str, int], delta: Mapping[str, Any]) -> Dict[str, int]:
    result = dict(currency)
    for key, value in _safe_dict(delta).items():
        result[str(key)] = int(result.get(str(key), 0)) + int(value or 0)
    return result


def _has_enough_currency(currency: Dict[str, int], delta: Mapping[str, Any]) -> bool:
    for key, value in _safe_dict(delta).items():
        amount = int(value or 0)
        if amount < 0 and int(currency.get(str(key), 0)) + amount < 0:
            return False
    return True


def _inventory(state: Mapping[str, Any]) -> list[Dict[str, Any]]:
    raw = state.get("inventory") or state.get("items") or []
    if isinstance(raw, list):
        items: list[Dict[str, Any]] = []
        for item in raw:
            if isinstance(item, dict):
                items.append(dict(item))
            elif item:
                items.append({"id": str(item), "quantity": 1})
        return items
    if isinstance(raw, dict):
        return [{"id": str(k), "quantity": int(v or 1)} for k, v in raw.items() if v]
    return []


def _add_items(inventory: list[Dict[str, Any]], items: list[Any]) -> list[Dict[str, Any]]:
    result = [dict(item) for item in inventory]
    for raw in items:
        item = _safe_dict(raw)
        item_id = _safe_str(item.get("id") or item.get("item_id"))
        if not item_id:
            continue
        quantity = int(item.get("quantity") or 1)
        for existing in result:
            if existing.get("id") == item_id:
                existing["quantity"] = int(existing.get("quantity", 0)) + quantity
                break
        else:
            result.append({"id": item_id, "quantity": quantity})
    return result


def _remove_items(inventory: list[Dict[str, Any]], items: list[Any]) -> list[Dict[str, Any]]:
    result = [dict(item) for item in inventory]
    for raw in items:
        item = _safe_dict(raw)
        item_id = _safe_str(item.get("id") or item.get("item_id"))
        if not item_id:
            continue
        quantity = int(item.get("quantity") or 1)
        for existing in result:
            if existing.get("id") == item_id:
                existing["quantity"] = max(0, int(existing.get("quantity", 0)) - quantity)
                if existing["quantity"] <= 0:
                    result.remove(existing)
                break
    return result


def resolve_mechanic_opportunity(
    *,
    player_input: str,
    state: Mapping[str, Any],
    scenario_state: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Resolve a player action that matches a deterministic mechanic opportunity.
    Returns turn_contract and state_delta effects.
    """
    match = match_mechanic_opportunity(
        player_input=player_input,
        state=state,
        scenario_state=scenario_state,
    )

    if not match.get("ok"):
        return {
            "ok": False,
            "reason": match.get("reason", "no_match"),
            "available_mechanics": match.get("available_mechanics", []),
        }

    opportunity = _safe_dict(match.get("opportunity"))
    resolver = _safe_str(opportunity.get("resolver"))
    effects = _safe_dict(opportunity.get("effects_preview"))
    metadata = _safe_dict(opportunity.get("metadata"))

    # Validate prerequisites
    currency = _currency(state)
    flags = _flags(state)
    currency_delta = _safe_dict(effects.get("currency_delta"))
    if not _has_enough_currency(currency, currency_delta):
        return {
            "ok": False,
            "reason": "insufficient_currency",
            "opportunity": opportunity,
        }

    # Apply effects based on resolver type
    turn_contract: Dict[str, Any] = {}
    state_delta: Dict[str, Any] = {}

    if resolver == "service_purchase":
        turn_contract.update({
            "service_result": _safe_dict(effects.get("service_result")),
            "currency_delta": currency_delta,
        })
        state_delta.update({
            "currency_delta": currency_delta,
        })

    elif resolver == "merchant_purchase":
        turn_contract.update({
            "purchase_result": _safe_dict(effects.get("purchase_result")),
            "currency_delta": currency_delta,
            "inventory_delta": _safe_dict(effects.get("inventory_delta")),
        })
        state_delta.update({
            "currency_delta": currency_delta,
            "inventory_delta": _safe_dict(effects.get("inventory_delta")),
        })

    elif resolver == "merchant_sale":
        turn_contract.update({
            "sale_result": _safe_dict(effects.get("sale_result")),
            "currency_delta": currency_delta,
            "inventory_delta": _safe_dict(effects.get("inventory_delta")),
        })
        state_delta.update({
            "currency_delta": currency_delta,
            "inventory_delta": _safe_dict(effects.get("inventory_delta")),
        })

    elif resolver == "party_recruitment":
        party_delta = _safe_dict(effects.get("party_delta"))
        companion_id = _safe_str(metadata.get("companion_id"))
        if companion_id:
            flags[f"party:{companion_id}_joined"] = True

        turn_contract.update({
            "party_delta": party_delta,
        })
        state_delta.update({
            "party_delta": party_delta,
            "flags": flags,
        })

    elif resolver == "travel":
        turn_contract.update({
            "travel_result": _safe_dict(effects.get("travel_result")),
        })
        state_delta.update({
            "location_changed": True,
            "current_location": _safe_str(metadata.get("to_location")),
        })

    elif resolver == "combat_start":
        encounter_id = _safe_str(metadata.get("encounter_id"))
        if encounter_id:
            flags[f"{encounter_id}.started"] = True

        turn_contract.update({
            "combat_result": _safe_dict(effects.get("combat_result")),
        })
        state_delta.update({
            "combat_started": True,
            "current_encounter": encounter_id,
            "flags": flags,
        })

    elif resolver == "combat_resolve":
        encounter_id = _safe_str(metadata.get("encounter_id"))
        if encounter_id:
            flags[f"{encounter_id}.resolved"] = True

        xp_delta = int(effects.get("xp_delta") or 0)
        current_xp = int(state.get("xp") or 0)
        next_xp = current_xp + xp_delta
        if next_xp >= 25:
            flags["xp:level_2_ready"] = True

        turn_contract.update({
            "combat_result": _safe_dict(effects.get("combat_result")),
            "xp_delta": xp_delta,
            "loot_result": _safe_dict(effects.get("loot_result")),
            "inventory_delta": _safe_dict(effects.get("inventory_delta")),
        })
        state_delta.update({
            "xp_delta": xp_delta,
            "xp": next_xp,
            "inventory_delta": _safe_dict(effects.get("inventory_delta")),
            "combat_resolved": True,
            "flags": flags,
        })

    elif resolver == "level_up":
        flags["player:level_2"] = True
        level_delta = _safe_dict(effects.get("level_delta"))
        turn_contract.update({
            "level_up": effects.get("level_up"),
            "level_delta": level_delta,
        })
        state_delta.update({
            "level_up": effects.get("level_up"),
            "level_delta": level_delta,
            "level": int(level_delta.get("new_level") or 2),
            "flags": flags,
        })

    elif resolver == "quest_turn_in":
        turn_contract.update({
            "quest_log_delta": _safe_dict(effects.get("quest_log_delta")),
            "xp_delta": effects.get("xp_delta"),
        })
        state_delta.update({
            "xp_delta": effects.get("xp_delta"),
            "quest_log_delta": _safe_dict(effects.get("quest_log_delta")),
        })

    mechanic = _safe_str(opportunity.get("mechanic"))
    result = {
        **turn_contract,
        "ok": True,
        "action_type": "mechanic",
        "semantic_action_type": mechanic,
        "mechanic": mechanic,
        "resolver": resolver,
        "opportunity_id": opportunity.get("id"),
        "meaningful_progress": True,
        "progress_category": (
            "location_progression"
            if mechanic == "travel"
            else f"{mechanic}_progress"
        ),
        "summary": f"Resolved mechanic opportunity: {opportunity.get('label')}.",
        "mechanics_evidence_source": "mechanic_opportunity_resolver",
    }

    return {
        "ok": True,
        "opportunity": opportunity,
        "result": result,
        "turn_contract": {
            **turn_contract,
            "mechanic": mechanic,
            "mechanics_evidence_source": "mechanic_opportunity_resolver",
        },
        "state_delta": {
            **state_delta,
            "mechanics_evidence_source": "mechanic_opportunity_resolver",
        },
        "mechanic": mechanic,
        "meaningful_progress": True,
        "progress_category": result["progress_category"],
        "mechanics_evidence_source": "mechanic_opportunity_resolver",
    }