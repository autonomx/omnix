from __future__ import annotations

from typing import Any, Dict

from app.rpg.companions.offers import evaluate_companion_offer
from app.rpg.companions.party import get_party_member
from app.rpg.dialogue_context.arc_context import build_arc_dialogue_context
from app.rpg.npc_evolution.state import get_npc_evolution
from app.rpg.social.reputation import get_relationship


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def build_npc_runtime_context(
    simulation_state: Dict[str, Any],
    npc_id: str,
    *,
    arc_id: str = "",
    topic_lore_id: str = "",
) -> Dict[str, Any]:
    npc_id = str(npc_id or "")
    evolution = get_npc_evolution(simulation_state, npc_id) or {}
    relationship = get_relationship(simulation_state, npc_id)
    dialogue_context = build_arc_dialogue_context(
        simulation_state,
        npc_id,
        arc_id=arc_id,
        topic_lore_id=topic_lore_id,
    )
    companion_offer = evaluate_companion_offer(
        simulation_state,
        npc_id,
        arc_id=arc_id,
    )
    party_member = get_party_member(simulation_state, npc_id)
    return {
        "ok": True,
        "npc_id": npc_id,
        "profession": evolution.get("profession") or "",
        "role": evolution.get("role") or "",
        "motivation": evolution.get("motivation") or "",
        "active_arcs": list(evolution.get("active_arcs") or [])[:10],
        "completed_arcs": list(evolution.get("completed_arcs") or [])[:10],
        "personality": dict(_safe_dict(evolution.get("personality"))),
        "flags": dict(_safe_dict(evolution.get("flags"))),
        "relationship": {
            "trust": int(relationship.get("trust") or 0),
            "fear": int(relationship.get("fear") or 0),
            "respect": int(relationship.get("respect") or 0),
            "hostility": int(relationship.get("hostility") or 0),
            "reputation": int(relationship.get("reputation") or 0),
        },
        "dialogue_context": dialogue_context,
        "companion_offer": {
            "eligible": bool(companion_offer.get("eligible")),
            "reason": companion_offer.get("reason"),
            "offer_id": companion_offer.get("offer_id") or companion_offer.get("context", {}).get("offer_id"),
        },
        "party_member": party_member,
        "bounded": {
            "max_active_arcs": 10,
            "max_completed_arcs": 10,
        },
    }