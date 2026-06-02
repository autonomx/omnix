from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from app.rpg.quests.givers import register_quest_offer
from app.rpg.quests.templates import get_quest_template

SOURCE = "deterministic_rumor_quest_runtime"


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


def ensure_rumor_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(simulation_state, dict):
        raise TypeError("simulation_state_must_be_dict")
    state = normalize_rumor_state(simulation_state.get("rumor_state"))
    simulation_state["rumor_state"] = state
    return state


def normalize_rumor_state(value: Dict[str, Any] | None = None) -> Dict[str, Any]:
    value = _safe_dict(value)
    rumors = {}
    for rumor_id, rumor in _safe_dict(value.get("rumors")).items():
        normalized = normalize_rumor(rumor, rumor_id=_safe_str(rumor_id))
        if normalized.get("rumor_id"):
            rumors[normalized["rumor_id"]] = normalized
    return {"version": 1, "rumors": rumors, "source": SOURCE}


def normalize_rumor(value: Dict[str, Any], *, rumor_id: str = "") -> Dict[str, Any]:
    value = _safe_dict(value)
    normalized_id = _safe_str(value.get("rumor_id")) or rumor_id
    status = _safe_str(value.get("status")) or "heard"
    if status not in {"heard", "backed", "converted", "dismissed"}:
        status = "heard"
    evidence = [normalize_rumor_evidence(row) for row in _safe_list(value.get("evidence")) if isinstance(row, dict)]
    return {
        "rumor_id": normalized_id,
        "summary": _safe_str(value.get("summary")) or normalized_id,
        "quest_id": _safe_str(value.get("quest_id")),
        "giver_id": _safe_str(value.get("giver_id")),
        "location_id": _safe_str(value.get("location_id")),
        "status": status,
        "heard_turn": _safe_int(value.get("heard_turn"), 0),
        "backed_turn": _safe_int(value.get("backed_turn"), 0),
        "converted_turn": _safe_int(value.get("converted_turn"), 0),
        "evidence": evidence,
        "source": _safe_str(value.get("source")) or SOURCE,
    }


def normalize_rumor_evidence(value: Dict[str, Any]) -> Dict[str, Any]:
    value = _safe_dict(value)
    return {
        "evidence_id": _safe_str(value.get("evidence_id")),
        "source_id": _safe_str(value.get("source_id")),
        "kind": _safe_str(value.get("kind")) or "witness",
        "summary": _safe_str(value.get("summary")),
        "turn_index": _safe_int(value.get("turn_index"), 0),
        "source": _safe_str(value.get("source")) or SOURCE,
    }


def register_rumor(
    simulation_state: Dict[str, Any],
    *,
    rumor_id: str,
    summary: str,
    quest_id: str = "",
    giver_id: str = "",
    location_id: str = "",
    turn_index: int = 0,
) -> Dict[str, Any]:
    normalized_id = _safe_str(rumor_id)
    if not normalized_id:
        return _reject("rumor_id_missing", rumor_id="")
    state = ensure_rumor_state(simulation_state)
    rumors = state.setdefault("rumors", {})
    existing = _safe_dict(rumors.get(normalized_id))
    if existing:
        return {"ok": True, "reason": "rumor_already_registered", "rumor": deepcopy(existing), "source": SOURCE}
    rumor = normalize_rumor(
        {
            "rumor_id": normalized_id,
            "summary": summary,
            "quest_id": quest_id,
            "giver_id": giver_id,
            "location_id": location_id,
            "status": "heard",
            "heard_turn": turn_index,
            "source": SOURCE,
        }
    )
    rumors[normalized_id] = rumor
    return {"ok": True, "reason": "rumor_registered", "rumor": deepcopy(rumor), "source": SOURCE}


def back_rumor_with_evidence(
    simulation_state: Dict[str, Any],
    *,
    rumor_id: str,
    evidence_id: str,
    source_id: str,
    summary: str,
    kind: str = "witness",
    turn_index: int = 0,
) -> Dict[str, Any]:
    state = ensure_rumor_state(simulation_state)
    rumor = _safe_dict(state.setdefault("rumors", {}).get(rumor_id))
    if not rumor:
        return _reject("rumor_missing", rumor_id=rumor_id)
    normalized_evidence_id = _safe_str(evidence_id)
    if not normalized_evidence_id:
        return _reject("evidence_id_missing", rumor_id=rumor_id)
    evidence = [normalize_rumor_evidence(row) for row in _safe_list(rumor.get("evidence")) if isinstance(row, dict)]
    if any(row.get("evidence_id") == normalized_evidence_id for row in evidence):
        rumor["evidence"] = evidence
        return {"ok": True, "reason": "duplicate_evidence_ignored", "rumor": deepcopy(rumor), "source": SOURCE}
    evidence.append(
        normalize_rumor_evidence(
            {
                "evidence_id": normalized_evidence_id,
                "source_id": source_id,
                "kind": kind,
                "summary": summary,
                "turn_index": turn_index,
                "source": SOURCE,
            }
        )
    )
    rumor["evidence"] = evidence
    rumor["status"] = "backed"
    rumor["backed_turn"] = _safe_int(turn_index, 0)
    rumor["source"] = SOURCE
    return {"ok": True, "reason": "rumor_backed", "rumor": deepcopy(rumor), "source": SOURCE}


def convert_rumor_to_quest_offer(
    simulation_state: Dict[str, Any],
    *,
    rumor_id: str,
    turn_index: int = 0,
) -> Dict[str, Any]:
    state = ensure_rumor_state(simulation_state)
    rumor = _safe_dict(state.setdefault("rumors", {}).get(rumor_id))
    if not rumor:
        return _reject("rumor_missing", rumor_id=rumor_id)
    if rumor.get("status") not in {"backed", "converted"}:
        return _reject("rumor_not_backed", rumor_id=rumor_id)
    quest_id = _safe_str(rumor.get("quest_id"))
    giver_id = _safe_str(rumor.get("giver_id"))
    if not quest_id:
        return _reject("quest_id_missing", rumor_id=rumor_id)
    template = get_quest_template(quest_id)
    if not template:
        return _reject("quest_template_missing", rumor_id=rumor_id)
    giver_id = giver_id or _safe_str(template.get("giver_id"))
    if not giver_id:
        return _reject("giver_id_missing", rumor_id=rumor_id)
    offer_result = register_quest_offer(simulation_state, giver_id=giver_id, quest_id=quest_id, turn_index=turn_index)
    if not offer_result.get("ok"):
        return {"ok": False, "reason": _safe_str(offer_result.get("reason")) or "quest_offer_rejected", "rumor_id": rumor_id, "offer_result": offer_result, "source": SOURCE}
    rumor["status"] = "converted"
    rumor["converted_turn"] = _safe_int(turn_index, 0)
    rumor["source"] = SOURCE
    return {"ok": True, "reason": "rumor_converted_to_quest_offer", "rumor": deepcopy(rumor), "offer_result": offer_result, "source": SOURCE}


def propagate_backed_rumors(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    state = ensure_rumor_state(simulation_state)
    backed = []
    for rumor in state.get("rumors", {}).values():
        rumor = _safe_dict(rumor)
        if rumor.get("status") in {"backed", "converted"} and rumor.get("evidence"):
            backed.append(
                {
                    "rumor_id": rumor.get("rumor_id"),
                    "quest_id": rumor.get("quest_id"),
                    "summary": rumor.get("summary"),
                    "evidence_count": len(_safe_list(rumor.get("evidence"))),
                    "status": rumor.get("status"),
                }
            )
    return {"ok": True, "reason": "backed_rumors_propagated", "backed_rumors": backed, "source": SOURCE}


def build_rumor_summary(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    state = normalize_rumor_state(_safe_dict(simulation_state).get("rumor_state"))
    rumors = list(state.get("rumors", {}).values())
    return {
        "source": SOURCE,
        "rumor_count": len(rumors),
        "backed_count": len([row for row in rumors if row.get("status") in {"backed", "converted"}]),
        "converted_count": len([row for row in rumors if row.get("status") == "converted"]),
        "rumors": deepcopy(rumors),
    }


def _reject(reason: str, *, rumor_id: str) -> Dict[str, Any]:
    return {"ok": False, "reason": reason, "rumor_id": rumor_id, "source": SOURCE}
