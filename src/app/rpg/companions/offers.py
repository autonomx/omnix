from __future__ import annotations

import hashlib
import json
from typing import Any, Dict

from app.rpg.companions.party import (
    add_party_member,
    append_companion_offer_history,
    ensure_party_state,
    has_companion_offer_status,
    is_party_member,
)
from app.rpg.npc_evolution.state import (
    apply_npc_evolution_delta,
    get_npc_evolution,
)
from app.rpg.social.reputation import get_relationship


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _stable_offer_id(npc_id: str, arc_id: str = "", motivation: str = "") -> str:
    payload = json.dumps(
        {
            "npc_id": npc_id,
            "arc_id": arc_id,
            "motivation": motivation,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    return f"companion_offer:{digest}"


def build_companion_offer_context(
    simulation_state: Dict[str, Any],
    npc_id: str,
    *,
    arc_id: str = "",
) -> Dict[str, Any]:
    npc_id = str(npc_id or "")
    evolution = get_npc_evolution(simulation_state, npc_id) or {}
    relationship = get_relationship(simulation_state, npc_id)
    active_arcs = list(evolution.get("active_arcs") or [])
    completed_arcs = list(evolution.get("completed_arcs") or [])
    motivation = _safe_str(evolution.get("motivation"))
    role = _safe_str(evolution.get("role"))
    profession = _safe_str(evolution.get("profession"))
    flags = dict(_safe_dict(evolution.get("flags")))
    personality = dict(_safe_dict(evolution.get("personality")))
    offer_id = _stable_offer_id(npc_id, arc_id or (active_arcs[0] if active_arcs else ""), motivation)
    return {
        "ok": True,
        "npc_id": npc_id,
        "offer_id": offer_id,
        "arc_id": arc_id,
        "active_arcs": active_arcs[:10],
        "completed_arcs": completed_arcs[:10],
        "profession": profession,
        "role": role,
        "motivation": motivation,
        "personality": personality,
        "flags": flags,
        "relationship": {
            "trust": int(relationship.get("trust") or 0),
            "fear": int(relationship.get("fear") or 0),
            "respect": int(relationship.get("respect") or 0),
            "hostility": int(relationship.get("hostility") or 0),
            "reputation": int(relationship.get("reputation") or 0),
        },
        "companion_eligible": bool(evolution.get("companion_eligible")),
        "companion_offered": bool(evolution.get("companion_offered")),
        "is_party_member": is_party_member(simulation_state, npc_id),
        "bounded": {
            "max_active_arcs": 10,
            "max_completed_arcs": 10,
        },
    }


def evaluate_companion_offer(
    simulation_state: Dict[str, Any],
    npc_id: str,
    *,
    arc_id: str = "",
    min_trust: int = 70,
    max_hostility: int = 40,
) -> Dict[str, Any]:
    ensure_party_state(simulation_state)
    context = build_companion_offer_context(simulation_state, npc_id, arc_id=arc_id)
    offer_id = context["offer_id"]
    relationship = context["relationship"]

    if not npc_id:
        return {"ok": False, "eligible": False, "reason": "missing_npc_id", "context": context}
    if context.get("is_party_member"):
        return {"ok": True, "eligible": False, "reason": "already_party_member", "context": context}
    if has_companion_offer_status(simulation_state, offer_id=offer_id, status="accepted"):
        return {"ok": True, "eligible": False, "reason": "offer_already_accepted", "context": context}
    if has_companion_offer_status(simulation_state, offer_id=offer_id, status="refused"):
        return {"ok": True, "eligible": False, "reason": "offer_previously_refused", "context": context}
    if not context.get("companion_eligible"):
        return {"ok": True, "eligible": False, "reason": "npc_not_companion_eligible", "context": context}
    if relationship["trust"] < int(min_trust or 0):
        return {
            "ok": True,
            "eligible": False,
            "reason": "trust_too_low",
            "context": context,
            "minimum_trust": int(min_trust or 0),
        }
    if relationship["hostility"] > int(max_hostility or 0):
        return {
            "ok": True,
            "eligible": False,
            "reason": "hostility_too_high",
            "context": context,
            "maximum_hostility": int(max_hostility or 0),
        }
    if not context.get("active_arcs") and not context.get("motivation"):
        return {"ok": True, "eligible": False, "reason": "no_active_arc_or_motivation", "context": context}

    return {
        "ok": True,
        "eligible": True,
        "reason": "eligible",
        "offer_id": offer_id,
        "context": context,
    }


def accept_companion_offer(
    simulation_state: Dict[str, Any],
    npc_id: str,
    *,
    arc_id: str = "",
    turn_index: int = 0,
    min_trust: int = 70,
    max_hostility: int = 40,
) -> Dict[str, Any]:
    evaluation = evaluate_companion_offer(
        simulation_state,
        npc_id,
        arc_id=arc_id,
        min_trust=min_trust,
        max_hostility=max_hostility,
    )
    if not evaluation.get("eligible"):
        append_companion_offer_history(
            simulation_state,
            offer_id=evaluation.get("context", {}).get("offer_id", ""),
            npc_id=npc_id,
            status="blocked",
            turn_index=turn_index,
            reason=evaluation.get("reason") or "not_eligible",
            details={"evaluation": evaluation},
        )
        return {
            "ok": False,
            "reason": "not_eligible",
            "evaluation": evaluation,
        }

    context = evaluation["context"]
    offer_id = evaluation["offer_id"]
    party_result = add_party_member(
        simulation_state,
        npc_id=npc_id,
        role=context.get("role") or "companion",
        motivation=context.get("motivation") or "",
        source_offer_id=offer_id,
        turn_index=turn_index,
        metadata={"arc_id": arc_id, "source": "companion_offer_v1"},
    )
    if not party_result.get("ok"):
        append_companion_offer_history(
            simulation_state,
            offer_id=offer_id,
            npc_id=npc_id,
            status="blocked",
            turn_index=turn_index,
            reason=party_result.get("reason") or "party_add_failed",
            details={"party_result": party_result},
        )
        return {
            "ok": False,
            "reason": "party_add_failed",
            "evaluation": evaluation,
            "party_result": party_result,
        }

    evolution_result = apply_npc_evolution_delta(
        simulation_state,
        npc_id,
        companion_offered=True,
        flags={"joined_party": True},
        source_event_id=offer_id,
        turn_index=turn_index,
    )
    history_result = append_companion_offer_history(
        simulation_state,
        offer_id=offer_id,
        npc_id=npc_id,
        status="accepted",
        turn_index=turn_index,
        reason="accepted",
        details={"party_result": party_result, "evolution_result": evolution_result},
    )
    return {
        "ok": True,
        "reason": "accepted",
        "offer_id": offer_id,
        "npc_id": npc_id,
        "evaluation": evaluation,
        "party_result": party_result,
        "evolution_result": evolution_result,
        "history_result": history_result,
    }


def refuse_companion_offer(
    simulation_state: Dict[str, Any],
    npc_id: str,
    *,
    arc_id: str = "",
    turn_index: int = 0,
    reason: str = "player_refused",
) -> Dict[str, Any]:
    context = build_companion_offer_context(simulation_state, npc_id, arc_id=arc_id)
    offer_id = context["offer_id"]
    if has_companion_offer_status(simulation_state, offer_id=offer_id, status="accepted"):
        return {
            "ok": False,
            "reason": "offer_already_accepted",
            "offer_id": offer_id,
            "context": context,
        }
    evolution_result = apply_npc_evolution_delta(
        simulation_state,
        npc_id,
        companion_offered=True,
        flags={"companion_offer_refused": True},
        source_event_id=offer_id,
        turn_index=turn_index,
    )
    history_result = append_companion_offer_history(
        simulation_state,
        offer_id=offer_id,
        npc_id=npc_id,
        status="refused",
        turn_index=turn_index,
        reason=reason,
        details={"evolution_result": evolution_result},
    )
    return {
        "ok": True,
        "reason": "refused",
        "offer_id": offer_id,
        "npc_id": npc_id,
        "context": context,
        "evolution_result": evolution_result,
        "history_result": history_result,
    }