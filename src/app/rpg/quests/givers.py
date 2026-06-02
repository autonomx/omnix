from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from app.rpg.quests.conditions import evaluate_all_quest_conditions
from app.rpg.quests.state import start_quest
from app.rpg.quests.templates import get_quest_template, quest_template_to_start_payload

SOURCE = "deterministic_quest_giver_state"


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def normalize_quest_giver_state(value: Dict[str, Any] | None = None) -> Dict[str, Any]:
    value = _safe_dict(value)
    givers: Dict[str, Any] = {}
    for giver_id, giver in _safe_dict(value.get("givers")).items():
        giver = _safe_dict(giver)
        normalized_id = _safe_str(giver.get("giver_id")) or _safe_str(giver_id)
        if not normalized_id:
            continue
        offers = {}
        for quest_id, offer in _safe_dict(giver.get("offers")).items():
            offer = _safe_dict(offer)
            normalized_quest_id = _safe_str(offer.get("quest_id")) or _safe_str(quest_id)
            if not normalized_quest_id:
                continue
            status = _safe_str(offer.get("status")) or "available"
            if status not in {"available", "offered", "accepted", "completed", "locked"}:
                status = "available"
            offers[normalized_quest_id] = {
                "quest_id": normalized_quest_id,
                "status": status,
                "offered_turn": _safe_int(offer.get("offered_turn"), 0),
                "accepted_turn": _safe_int(offer.get("accepted_turn"), 0),
                "source": _safe_str(offer.get("source")) or SOURCE,
            }
        givers[normalized_id] = {
            "giver_id": normalized_id,
            "offers": offers,
            "source": _safe_str(giver.get("source")) or SOURCE,
        }
    return {"version": 1, "givers": givers, "source": SOURCE}


def ensure_quest_giver_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(simulation_state, dict):
        raise TypeError("simulation_state_must_be_dict")
    state = normalize_quest_giver_state(simulation_state.get("quest_giver_state"))
    simulation_state["quest_giver_state"] = state
    return state


def register_quest_offer(
    simulation_state: Dict[str, Any],
    *,
    giver_id: str,
    quest_id: str,
    turn_index: int = 0,
) -> Dict[str, Any]:
    template = get_quest_template(quest_id)
    if not template:
        return {"ok": False, "reason": "quest_template_missing", "giver_id": giver_id, "quest_id": quest_id, "source": SOURCE}
    expected_giver = _safe_str(template.get("giver_id"))
    if expected_giver and expected_giver != giver_id:
        return {"ok": False, "reason": "quest_giver_mismatch", "giver_id": giver_id, "expected_giver_id": expected_giver, "quest_id": quest_id, "source": SOURCE}

    giver_state = ensure_quest_giver_state(simulation_state)
    givers = giver_state.setdefault("givers", {})
    giver = givers.setdefault(giver_id, {"giver_id": giver_id, "offers": {}, "source": SOURCE})
    offer = giver.setdefault("offers", {}).setdefault(
        quest_id,
        {"quest_id": quest_id, "status": "available", "offered_turn": 0, "accepted_turn": 0, "source": SOURCE},
    )
    if offer.get("status") == "available":
        offer["status"] = "offered"
        offer["offered_turn"] = _safe_int(turn_index, 0)
    return {"ok": True, "reason": "quest_offer_registered", "giver_id": giver_id, "quest_id": quest_id, "offer": deepcopy(offer), "template": template, "source": SOURCE}


def available_quest_offers(simulation_state: Dict[str, Any], *, giver_id: str) -> Dict[str, Any]:
    giver_state = ensure_quest_giver_state(simulation_state)
    giver = _safe_dict(_safe_dict(giver_state.get("givers")).get(giver_id))
    offers = []
    for quest_id, offer in sorted(_safe_dict(giver.get("offers")).items()):
        offer = _safe_dict(offer)
        if offer.get("status") in {"available", "offered"}:
            template = get_quest_template(quest_id)
            condition_result = evaluate_all_quest_conditions(simulation_state, _safe_list(template.get("prerequisites"))) if template else {"ok": False, "failed": []}
            offers.append({"quest_id": quest_id, "status": offer.get("status"), "available": bool(condition_result.get("ok")), "conditions": condition_result, "template": template, "source": SOURCE})
    return {"ok": True, "giver_id": giver_id, "offers": offers, "source": SOURCE}


def accept_quest_offer(
    simulation_state: Dict[str, Any],
    *,
    giver_id: str,
    quest_id: str,
    turn_index: int = 0,
) -> Dict[str, Any]:
    template = get_quest_template(quest_id)
    if not template:
        return {"ok": False, "reason": "quest_template_missing", "giver_id": giver_id, "quest_id": quest_id, "source": SOURCE}
    condition_result = evaluate_all_quest_conditions(simulation_state, _safe_list(template.get("prerequisites")))
    if not condition_result.get("ok"):
        return {"ok": False, "reason": "quest_prerequisites_failed", "giver_id": giver_id, "quest_id": quest_id, "conditions": condition_result, "source": SOURCE}

    register_quest_offer(simulation_state, giver_id=giver_id, quest_id=quest_id, turn_index=turn_index)
    giver_state = ensure_quest_giver_state(simulation_state)
    offer = giver_state["givers"][giver_id]["offers"][quest_id]
    if offer.get("status") == "accepted":
        return {"ok": True, "reason": "quest_offer_already_accepted", "giver_id": giver_id, "quest_id": quest_id, "offer": deepcopy(offer), "source": SOURCE}

    payload = quest_template_to_start_payload(template)
    start_result = start_quest(
        simulation_state,
        quest_id,
        title=payload["title"],
        stage=payload["stage"],
        objectives=payload["objectives"],
        turn_index=turn_index,
    )
    quest = start_result.get("quest", {})
    quest.setdefault("metadata", {}).update(payload.get("metadata", {}))
    quest["rewards"] = list(payload.get("rewards", []))
    offer["status"] = "accepted"
    offer["accepted_turn"] = _safe_int(turn_index, 0)
    return {"ok": True, "reason": "quest_offer_accepted", "giver_id": giver_id, "quest_id": quest_id, "offer": deepcopy(offer), "quest_start": start_result, "source": SOURCE}
