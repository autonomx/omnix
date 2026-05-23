from __future__ import annotations

"""N127.10 survival promotion cadence and critical-thirst hard override.

Selector-only fixes were insufficient in 100-turn runs because survival
suggestions could exist without being promoted frequently enough.  This module
runs after calibrated survival persistence, where authoritative needs, explicit
inventory supplies, and the deterministic resolver are all visible together.
It does not use an LLM and does not fabricate hidden effects: drink relief is
applied only by adding/using explicit N127.6/N127.8 inventory items and the
existing N123.2 resolver.
"""

import copy
from typing import Any, Dict, Tuple

from app.rpg.session.survival_actions import resolve_survival_action
from app.rpg.session.survival_autoplay_relief_supplies import ensure_survival_autoplay_relief_supplies
from app.rpg.session.survival_autoplay_persistence import (
    _climate_from_session,
    _patch_survival_action_result,
    _record_survival_accumulator,
    mirror_survival_state_into_session,
)

SOURCE = "n12710_survival_promotion_cadence"
OVERRIDE_SOURCE = "n12710_critical_thirst_hard_override"
THIRST_CRITICAL_THRESHOLD = 90
THIRST_CAPPED_THRESHOLD = 100
CAPPED_HARD_OVERRIDE_STREAK = 3


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _simulation_state(session: Dict[str, Any]) -> Dict[str, Any]:
    session = _safe_dict(session)
    sim = _safe_dict(session.get("simulation_state"))
    if sim:
        return sim
    state = _safe_dict(session.get("state"))
    return _safe_dict(state.get("simulation_state")) or state


def _runtime_state(session: Dict[str, Any]) -> Dict[str, Any]:
    session = _safe_dict(session)
    runtime = _safe_dict(session.get("runtime_state"))
    session["runtime_state"] = runtime
    return runtime


def _survival(session: Dict[str, Any]) -> Dict[str, Any]:
    climate = _climate_from_session(session)
    return _safe_dict(climate.get("survival"))


def _current_needs(session: Dict[str, Any]) -> Dict[str, int]:
    survival = _survival(session)
    sim = _simulation_state(session)
    resources = _safe_dict(_safe_dict(sim.get("player_state")).get("resources"))
    needs = _safe_dict(sim.get("needs"))
    return {
        "hunger": max(0, min(100, _safe_int(survival.get("hunger", resources.get("hunger", needs.get("hunger", 0))), 0))),
        "thirst": max(0, min(100, _safe_int(survival.get("thirst", resources.get("thirst", needs.get("thirst", 0))), 0))),
        "fatigue": max(0, min(100, _safe_int(survival.get("fatigue", resources.get("fatigue", needs.get("fatigue", 0))), 0))),
    }


def _turn_index(session: Dict[str, Any], result: Dict[str, Any]) -> int:
    for value in (
        _safe_dict(result).get("turn_index"),
        _safe_dict(result).get("turn"),
        _safe_dict(_safe_dict(result).get("turn_contract")).get("turn_index"),
        _survival(session).get("action_count"),
        _safe_dict(_safe_dict(_simulation_state(session).get("player_state")).get("resources")).get("action_count"),
    ):
        parsed = _safe_int(value, 0)
        if parsed:
            return parsed
    return 0


def _item_quantity(item: Dict[str, Any]) -> int:
    return max(0, _safe_int(_safe_dict(item).get("quantity", _safe_dict(item).get("qty", 1)), 1))


def _item_name(item: Dict[str, Any]) -> str:
    item = _safe_dict(item)
    return _safe_str(item.get("name") or item.get("label") or item.get("item_id") or item.get("id") or "water")


def _item_identity(item: Dict[str, Any]) -> str:
    item = _safe_dict(item)
    return _safe_str(item.get("item_id") or item.get("id") or item.get("key") or item.get("name")).lower()


def _item_tags(item: Dict[str, Any]) -> list[str]:
    item = _safe_dict(item)
    tags: list[str] = []
    for key in ("tags", "item_tags", "categories"):
        tags.extend(_safe_str(value).lower() for value in _safe_list(item.get(key)))
    kind = _safe_str(item.get("kind") or item.get("type") or item.get("category")).lower()
    if kind:
        tags.append(kind)
    return tags


def _is_drink_item(item: Dict[str, Any]) -> bool:
    item = _safe_dict(item)
    if _item_quantity(item) <= 0:
        return False
    haystack = " ".join([_item_identity(item), _item_name(item).lower()] + _item_tags(item))
    return any(term in haystack for term in ("drink", "water", "waterskin", "canteen", "ale", "wine", "beer"))


def _drink_item(session: Dict[str, Any]) -> Dict[str, Any]:
    sim = _simulation_state(session)
    inventory = _safe_dict(_safe_dict(sim.get("player_state")).get("inventory_state"))
    for raw in _safe_list(inventory.get("items")):
        item = _safe_dict(raw)
        if _is_drink_item(item):
            return dict(item)
    return {}


def _existing_action(result: Dict[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(result)
    contract = _safe_dict(result.get("turn_contract"))
    changes = _safe_dict(contract.get("resource_changes") or result.get("resource_changes"))
    effect = _safe_dict(contract.get("effect_result") or result.get("effect_result"))
    return _safe_dict(
        contract.get("survival_action")
        or result.get("survival_action")
        or changes.get("survival_action")
        or effect.get("survival_action")
    )


def _cadence_state(session: Dict[str, Any]) -> Dict[str, Any]:
    return dict(_safe_dict(_runtime_state(session).get("survival_autoplay_cadence_state")))


def _write_cadence_state(session: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    runtime = _runtime_state(session)
    runtime["survival_autoplay_cadence_state"] = copy.deepcopy(state)
    runtime["last_survival_autoplay_cadence_source"] = SOURCE
    session["runtime_state"] = runtime
    return session


def _update_cadence_state(
    session: Dict[str, Any],
    result: Dict[str, Any],
    *,
    before_needs: Dict[str, int],
    after_needs: Dict[str, int],
    override: Dict[str, Any],
) -> Dict[str, Any]:
    state = _cadence_state(session)
    turn_index = _turn_index(session, result)
    before_thirst = _safe_int(before_needs.get("thirst"), 0)
    after_thirst = _safe_int(after_needs.get("thirst"), 0)
    prev_capped = _safe_int(state.get("consecutive_thirst_capped_turns"), 0)
    capped_before = before_thirst >= THIRST_CAPPED_THRESHOLD
    capped_after = after_thirst >= THIRST_CAPPED_THRESHOLD
    state.update({
        "format_version": "n12710_survival_cadence_state_v1",
        "source": SOURCE,
        "turn_index": turn_index,
        "last_thirst_before": before_thirst,
        "last_thirst_after": after_thirst,
        "last_survival_relief_turn": turn_index if _safe_dict(override).get("applied") else state.get("last_survival_relief_turn", 0),
        "last_survival_relief_kind": _safe_str(_safe_dict(override).get("action_kind") or state.get("last_survival_relief_kind")),
        "last_drink_relief_turn": turn_index if _safe_dict(override).get("applied") else state.get("last_drink_relief_turn", 0),
        "consecutive_thirst_capped_turns": prev_capped + 1 if capped_before and capped_after else (1 if capped_before else 0),
        "critical_thirst_override_count": _safe_int(state.get("critical_thirst_override_count"), 0) + (1 if _safe_dict(override).get("applied") else 0),
        "last_critical_thirst_override": copy.deepcopy(override),
    })
    return _write_cadence_state(session, state)


def _patch_override_metadata(result: Dict[str, Any], override: Dict[str, Any], session: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(_safe_dict(result))
    override = copy.deepcopy(_safe_dict(override))
    cadence = copy.deepcopy(_cadence_state(session))
    result["survival_autoplay_critical_thirst_override"] = override
    result["survival_autoplay_cadence_state"] = cadence
    contract = dict(_safe_dict(result.get("turn_contract")))
    if contract:
        contract["survival_autoplay_critical_thirst_override"] = override
        contract["survival_autoplay_cadence_state"] = cadence
        result["turn_contract"] = contract
    payload = dict(_safe_dict(result.get("result")))
    if payload:
        payload["survival_autoplay_critical_thirst_override"] = override
        payload["survival_autoplay_cadence_state"] = cadence
        result["result"] = payload
    persistence = dict(_safe_dict(result.get("survival_autoplay_persistence")))
    if persistence:
        persistence["critical_thirst_override"] = override
        persistence["cadence_state"] = cadence
        result["survival_autoplay_persistence"] = persistence
    return result


def _maybe_save_session(session: Dict[str, Any], save: bool) -> None:
    if not save:
        return
    try:
        from app.rpg.session.service import save_session

        save_session(session)
    except Exception:
        pass


def apply_critical_thirst_hard_override(
    result: Dict[str, Any],
    *,
    session_key: str | None = None,
    save: bool = True,
) -> Dict[str, Any]:
    """Apply deterministic drink relief when critical thirst was missed.

    This is intentionally post-persistence: calibrated needs, explicit autoplay
    supplies, and the deterministic resolver are now all present.  The helper is
    conservative: it skips if thirst is below the critical threshold or if the
    current row already applied drink relief, but it may supersede rest/eat when
    thirst is at/near cap.
    """

    result = dict(_safe_dict(result))
    session = copy.deepcopy(_safe_dict(result.get("session")))
    if not session:
        override = {"applied": False, "reason": "missing_session", "source": OVERRIDE_SOURCE}
        result["survival_autoplay_critical_thirst_override"] = override
        return result

    before_needs = _current_needs(session)
    existing = _existing_action(result)
    existing_kind = _safe_str(existing.get("action_kind"))
    if existing.get("applied") and existing_kind in {"drink_water", "buy_drink"}:
        override = {
            "applied": False,
            "reason": "drink_already_applied",
            "source": OVERRIDE_SOURCE,
            "needs": before_needs,
            "existing_action_kind": existing_kind,
        }
        session = _update_cadence_state(session, result, before_needs=before_needs, after_needs=before_needs, override=override)
        result["session"] = session
        return _patch_override_metadata(result, override, session)

    thirst = _safe_int(before_needs.get("thirst"), 0)
    state = _cadence_state(session)
    capped_streak = _safe_int(state.get("consecutive_thirst_capped_turns"), 0)
    hard_due_to_streak = thirst >= THIRST_CAPPED_THRESHOLD and capped_streak + 1 >= CAPPED_HARD_OVERRIDE_STREAK
    if thirst < THIRST_CRITICAL_THRESHOLD and not hard_due_to_streak:
        override = {
            "applied": False,
            "reason": "thirst_below_critical_threshold",
            "source": OVERRIDE_SOURCE,
            "needs": before_needs,
            "consecutive_thirst_capped_turns": capped_streak,
        }
        session = _update_cadence_state(session, result, before_needs=before_needs, after_needs=before_needs, override=override)
        result["session"] = session
        return _patch_override_metadata(result, override, session)

    # Make sure a backed explicit drink exists.  This uses the bounded N127.6 /
    # N127.8 supply helper; if the per-session drink budget is exhausted, no
    # hidden relief is created.
    session, supply_summary = ensure_survival_autoplay_relief_supplies(session, session_key=session_key)
    drink = _drink_item(session)
    if not drink:
        override = {
            "applied": False,
            "reason": "critical_thirst_no_backed_drink_available",
            "source": OVERRIDE_SOURCE,
            "needs": before_needs,
            "supply_summary": supply_summary,
            "consecutive_thirst_capped_turns": capped_streak,
        }
        session = _update_cadence_state(session, result, before_needs=before_needs, after_needs=before_needs, override=override)
        result["session"] = session
        return _patch_override_metadata(result, override, session)

    command = f"I drink {_item_name(drink)}"
    simulation_state = _simulation_state(session)
    action = resolve_survival_action(player_input=command, simulation_state=simulation_state)
    action = dict(_safe_dict(action))
    after_climate = _safe_dict(simulation_state.get("climate_survival"))
    if after_climate:
        session = mirror_survival_state_into_session(session, after_climate)
    after_needs = _current_needs(session)
    override = {
        "applied": bool(action.get("applied")),
        "matched": bool(action.get("matched")),
        "reason": "critical_thirst_hard_override" if not hard_due_to_streak else "critical_thirst_capped_streak_hard_override",
        "source": OVERRIDE_SOURCE,
        "cadence_source": SOURCE,
        "needs_before": before_needs,
        "needs_after": after_needs,
        "command": command,
        "action_kind": _safe_str(action.get("action_kind")),
        "blocked": bool(action.get("blocked")),
        "blocked_reason": _safe_str(action.get("blocked_reason")),
        "drink_item_id": _safe_str(drink.get("item_id") or drink.get("id") or drink.get("name")),
        "supply_summary": supply_summary,
        "consecutive_thirst_capped_turns_before": capped_streak,
        "hard_due_to_streak": hard_due_to_streak,
        "existing_action_kind": existing_kind,
    }
    trigger = {
        "applied": bool(action.get("applied")),
        "matched": bool(action.get("matched")),
        "promoted_command": command,
        "promotion": {"source": OVERRIDE_SOURCE, "reason": override["reason"], "need": "thirst", "need_value": thirst},
        "action_kind": _safe_str(action.get("action_kind")),
        "blocked": bool(action.get("blocked")),
        "blocked_reason": _safe_str(action.get("blocked_reason")),
        "source": OVERRIDE_SOURCE,
    }
    if action.get("matched"):
        result = _patch_survival_action_result(result, action, trigger, _climate_from_session(session) or after_climate)
    session = _update_cadence_state(session, result, before_needs=before_needs, after_needs=after_needs, override=override)
    result["session"] = session
    result["simulation_state"] = _safe_dict(session.get("simulation_state"))
    result = _patch_override_metadata(result, override, session)
    _record_survival_accumulator(
        session_key,
        _climate_from_session(session),
        {"source": SOURCE, "critical_thirst_override": override, "calibrated": True},
    )
    _maybe_save_session(session, save)
    return result
