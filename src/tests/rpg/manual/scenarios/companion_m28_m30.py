from __future__ import annotations

from typing import Any, Dict


def _make_bran_eligible_setup(trust: int = 80, hostility: int = 0) -> Dict[str, Any]:
    return {
        "setup_social_state": {"relationships": {"bran": {"trust": trust, "hostility": hostility}}},
        "setup_npc_evolution_transitions": [
            {
                "action": "start_arc",
                "npc_id": "bran",
                "arc_id": "npc_arc:bran_revenge",
                "motivation": "revenge_against_red_sashes",
                "role": "companion",
                "profession": "former_innkeeper",
            },
            {
                "action": "evolve",
                "npc_id": "bran",
                "companion_eligible": True,
                "personality_deltas": {"vengeful": 20},
            },
        ],
    }


COMPANION_M28_M30_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "companion_offer_available_when_arc_and_trust_ready": {
        **_make_bran_eligible_setup(),
        "turns": ["I ask Bran if he wants to travel with me."],
        "checks": [
            {
                "type": "companion_offer_evaluate",
                "npc_id": "bran",
                "expected_eligible": True,
                "expected_reason": "eligible",
            },
            {
                "type": "companion_offer_context",
                "npc_id": "bran",
                "expected": {
                    "profession": "former_innkeeper",
                    "motivation": "revenge_against_red_sashes",
                    "companion_eligible": True,
                },
            },
        ],
    },
    "companion_offer_blocked_by_low_trust": {
        **_make_bran_eligible_setup(trust=20),
        "turns": ["I ask Bran to join despite low trust."],
        "checks": [
            {
                "type": "companion_offer_evaluate",
                "npc_id": "bran",
                "expected_eligible": False,
                "expected_reason": "trust_too_low",
            }
        ],
    },
    "companion_offer_blocked_by_hostility": {
        **_make_bran_eligible_setup(trust=80, hostility=80),
        "turns": ["I ask hostile Bran to join."],
        "checks": [
            {
                "type": "companion_offer_evaluate",
                "npc_id": "bran",
                "expected_eligible": False,
                "expected_reason": "hostility_too_high",
            }
        ],
    },
    "accepting_companion_offer_adds_party_member": {
        **_make_bran_eligible_setup(),
        "setup_companion_offer_actions": [
            {"action": "accept", "npc_id": "bran", "turn_index": 3}
        ],
        "turns": ["I check that Bran joined my party."],
        "checks": [
            {
                "type": "party_member",
                "npc_id": "bran",
                "expected_present": True,
                "expected": {
                    "status": "active",
                    "role": "companion",
                    "motivation": "revenge_against_red_sashes",
                },
            },
            {
                "type": "companion_offer_evaluate",
                "npc_id": "bran",
                "expected_eligible": False,
                "expected_reason": "already_party_member",
            },
        ],
    },
    "accepting_companion_offer_is_apply_once": {
        **_make_bran_eligible_setup(),
        "setup_companion_offer_actions": [
            {"action": "accept", "npc_id": "bran", "turn_index": 3}
        ],
        "turns": ["I try to accept Bran twice."],
        "checks": [
            {
                "type": "companion_offer_accept",
                "npc_id": "bran",
                "turn_index": 4,
                "expected_ok": False,
                "expected_reason": "not_eligible",
            },
            {
                "type": "party_member",
                "npc_id": "bran",
                "expected_present": True,
            },
        ],
    },
    "refusing_companion_offer_blocks_future_offer": {
        **_make_bran_eligible_setup(),
        "setup_companion_offer_actions": [
            {"action": "refuse", "npc_id": "bran", "turn_index": 3}
        ],
        "turns": ["I check that Bran's refused offer stays refused."],
        "checks": [
            {
                "type": "companion_offer_evaluate",
                "npc_id": "bran",
                "expected_eligible": False,
                "expected_reason": "offer_previously_refused",
            },
            {
                "type": "party_member",
                "npc_id": "bran",
                "expected_present": False,
            },
        ],
    },
    "npc_runtime_context_exposes_evolution_and_offer": {
        **_make_bran_eligible_setup(),
        "turns": ["I inspect Bran's runtime context."],
        "checks": [
            {
                "type": "npc_runtime_context",
                "npc_id": "bran",
                "expected": {
                    "profession": "former_innkeeper",
                    "motivation": "revenge_against_red_sashes",
                },
                "expected_companion_eligible": True,
            }
        ],
    },
    "companion_offer_not_available_without_npc_arc": {
        "setup_social_state": {"relationships": {"bran": {"trust": 80}}},
        "setup_npc_evolution_transitions": [
            {
                "action": "evolve",
                "npc_id": "bran",
                "companion_eligible": True,
            }
        ],
        "turns": ["I ask Bran to join without an active motivation arc."],
        "checks": [
            {
                "type": "companion_offer_evaluate",
                "npc_id": "bran",
                "expected_eligible": False,
                "expected_reason": "no_active_arc_or_motivation",
            }
        ],
    },
}