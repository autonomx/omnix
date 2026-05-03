from __future__ import annotations

from typing import Any, Dict

SOCIAL_L10_L12_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "social_persuasion_success_high_trust": {
        "setup_social_state": {
            "relationships": {"bran": {"trust": 50, "reputation": 20, "hostility": 0}},
            "global_reputation": {"player": 5},
        },
        "setup_social_actions": [
            {
                "type": "persuasion",
                "result_key": "discount_room",
                "npc_id": "bran",
                "request": "discounted room",
                "difficulty": 40,
                "approach": "polite",
            }
        ],
        "turns": ["I politely ask Bran for a discounted room."],
        "checks": [
            {"type": "social_persuasion_result", "result_key": "discount_room", "expected_ok": True},
            {"type": "social_relationship", "npc_id": "bran", "minimums": {"trust": 50}},
        ],
    },
    "social_persuasion_fails_low_trust": {
        "setup_social_state": {
            "relationships": {"bran": {"trust": -30, "hostility": 30}},
        },
        "setup_social_actions": [
            {
                "type": "persuasion",
                "result_key": "free_room",
                "npc_id": "bran",
                "request": "free room",
                "difficulty": 80,
                "approach": "polite",
            }
        ],
        "turns": ["I ask Bran for a free room despite him distrusting me."],
        "checks": [
            {"type": "social_persuasion_result", "result_key": "free_room", "expected_ok": False},
            {"type": "social_relationship", "npc_id": "bran", "minimums": {"hostility": 30}},
        ],
    },
    "social_intimidation_creates_fear_but_lowers_trust": {
        "setup_social_state": {
            "relationships": {"bran": {"trust": 20, "fear": 0, "hostility": 0}},
        },
        "setup_social_profiles": {
            "bran": {"bravery": 35, "stubbornness": 30},
        },
        "setup_social_actions": [
            {
                "type": "intimidation",
                "result_key": "threaten_bran",
                "npc_id": "bran",
                "threat": "I will expose your secret.",
                "severity": 90,
            }
        ],
        "turns": ["I threaten Bran with exposing his secret."],
        "checks": [
            {
                "type": "social_intimidation_result",
                "result_key": "threaten_bran",
                "expected_ok": True,
                "expected_stance": "fearful",
            },
            {"type": "social_relationship", "npc_id": "bran", "minimums": {"fear": 10}, "maximums": {"trust": 19}},
        ],
    },
    "social_failed_intimidation_escalates_hostility": {
        "setup_social_profiles": {
            "bran": {"bravery": 90, "stubbornness": 90},
        },
        "setup_social_actions": [
            {
                "type": "intimidation",
                "result_key": "weak_threat",
                "npc_id": "bran",
                "threat": "weak threat",
                "severity": 10,
            }
        ],
        "turns": ["I make a weak threat against Bran."],
        "checks": [
            {
                "type": "social_intimidation_result",
                "result_key": "weak_threat",
                "expected_ok": False,
                "expected_stance": "hostile",
                "expected_escalation": True,
            },
            {"type": "social_relationship", "npc_id": "bran", "minimums": {"hostility": 10}},
        ],
    },
    "social_valid_leverage_from_memory_improves_negotiation": {
        "setup_social_state": {
            "relationships": {"bran": {"trust": 0, "hostility": 0}},
        },
        "setup_social_leverage": [
            {
                "leverage_id": "lev:bran_debt",
                "npc_id": "bran",
                "kind": "debt",
                "summary": "Bran owes the player a favor.",
                "strength": 35,
                "valid": True,
                "tags": ["favor", "room"],
            }
        ],
        "setup_social_actions": [
            {
                "type": "persuasion",
                "result_key": "leverage_room",
                "npc_id": "bran",
                "request": "discounted room",
                "difficulty": 65,
                "approach": "logical",
                "leverage_id": "lev:bran_debt",
            }
        ],
        "turns": ["I remind Bran that he owes me a favor and ask for a discounted room."],
        "checks": [
            {"type": "social_leverage_valid", "npc_id": "bran", "leverage_id": "lev:bran_debt", "expected_ok": True, "request": "discounted room"},
            {"type": "social_persuasion_result", "result_key": "leverage_room", "expected_ok": True},
        ],
    },
    "social_invalid_leverage_rejected": {
        "setup_social_leverage": [
            {
                "leverage_id": "lev:fake",
                "npc_id": "bran",
                "kind": "secret",
                "summary": "Fake leverage.",
                "strength": 50,
                "valid": False,
            }
        ],
        "setup_social_actions": [
            {
                "type": "persuasion",
                "result_key": "fake_leverage",
                "npc_id": "bran",
                "request": "discounted room",
                "difficulty": 75,
                "approach": "logical",
                "leverage_id": "lev:fake",
            }
        ],
        "turns": ["I try to use fake leverage on Bran."],
        "checks": [
            {"type": "social_leverage_valid", "npc_id": "bran", "leverage_id": "lev:fake", "expected_ok": False},
            {"type": "social_persuasion_result", "result_key": "fake_leverage", "expected_ok": False},
        ],
    },
    "social_reputation_positive_unlocks_cooperation": {
        "setup_social_state": {
            "relationships": {"bran": {"trust": 10, "reputation": 50}},
            "global_reputation": {"player": 30},
        },
        "setup_social_actions": [
            {
                "type": "persuasion",
                "result_key": "positive_rep",
                "npc_id": "bran",
                "request": "information about the road",
                "difficulty": 45,
                "approach": "polite",
            }
        ],
        "turns": ["I ask Bran for information, relying on my good reputation."],
        "checks": [
            {"type": "social_persuasion_result", "result_key": "positive_rep", "expected_ok": True},
        ],
    },
    "social_reputation_negative_blocks_request": {
        "setup_social_state": {
            "relationships": {"bran": {"trust": -20, "hostility": 30, "reputation": -40}},
            "global_reputation": {"player": -30},
        },
        "setup_social_actions": [
            {
                "type": "persuasion",
                "result_key": "negative_rep",
                "npc_id": "bran",
                "request": "information about the road",
                "difficulty": 55,
                "approach": "polite",
            }
        ],
        "turns": ["I ask Bran for help despite my bad reputation."],
        "checks": [
            {"type": "social_persuasion_result", "result_key": "negative_rep", "expected_ok": False},
        ],
    },
    "social_public_threat_lowers_reputation_with_witnesses": {
        "setup_social_profiles": {"bran": {"bravery": 35, "stubbornness": 30}},
        "setup_social_actions": [
            {
                "type": "intimidation",
                "result_key": "public_threat",
                "npc_id": "bran",
                "threat": "public threat",
                "severity": 90,
                "witnesses": ["mira"],
            }
        ],
        "turns": ["I threaten Bran in front of Mira."],
        "checks": [
            {"type": "social_intimidation_result", "result_key": "public_threat", "expected_ok": True},
            {"type": "social_global_reputation", "actor_id": "player", "maximum": -1},
            {"type": "social_relationship", "npc_id": "mira", "maximums": {"trust": -1}},
        ],
    },
    "social_private_threat_affects_only_target": {
        "setup_social_profiles": {"bran": {"bravery": 35, "stubbornness": 30}},
        "setup_social_actions": [
            {
                "type": "intimidation",
                "result_key": "private_threat",
                "npc_id": "bran",
                "threat": "private threat",
                "severity": 90,
                "witnesses": [],
            }
        ],
        "turns": ["I threaten Bran privately."],
        "checks": [
            {"type": "social_intimidation_result", "result_key": "private_threat", "expected_ok": True},
            {"type": "social_global_reputation", "actor_id": "player", "expected": 0},
            {"type": "social_relationship", "npc_id": "bran", "minimums": {"fear": 10}},
            {"type": "social_relationship", "npc_id": "mira", "expected": {"trust": 0, "hostility": 0}},
        ],
    },
    "social_fearful_npc_complies_but_remembers_threat": {
        "setup_social_profiles": {"bran": {"bravery": 35, "stubbornness": 30}},
        "setup_social_actions": [
            {
                "type": "intimidation",
                "result_key": "fearful_comply",
                "npc_id": "bran",
                "threat": "I will ruin you.",
                "severity": 90,
            }
        ],
        "turns": ["I intimidate Bran into complying."],
        "checks": [
            {"type": "social_intimidation_result", "result_key": "fearful_comply", "expected_ok": True, "expected_stance": "fearful"},
            {"type": "social_stance", "npc_id": "bran", "expected_stance": "fearful"},
        ],
    },
    "social_trust_recovers_after_helpful_action": {
        "setup_social_state": {
            "relationships": {"bran": {"trust": -10, "hostility": 10}},
        },
        "setup_social_actions": [
            {
                "type": "persuasion",
                "result_key": "helpful_action",
                "npc_id": "bran",
                "request": "accept my apology after I helped clean the tavern",
                "difficulty": 35,
                "approach": "polite",
            }
        ],
        "turns": ["I apologize to Bran after helping clean the tavern."],
        "checks": [
            {"type": "social_persuasion_result", "result_key": "helpful_action", "expected_ok": True},
            {"type": "social_relationship", "npc_id": "bran", "minimums": {"trust": -8}},
        ],
    },
    "social_response_stance_reflected_in_contract": {
        "setup_social_state": {
            "relationships": {"bran": {"trust": 50, "reputation": 20}},
        },
        "setup_social_actions": [
            {
                "type": "persuasion",
                "result_key": "stance_contract",
                "npc_id": "bran",
                "request": "reasonable room discount",
                "difficulty": 40,
                "approach": "polite",
            }
        ],
        "turns": ["I ask Bran politely for a reasonable room discount."],
        "checks": [
            {"type": "social_persuasion_result", "result_key": "stance_contract", "expected_ok": True},
            {"type": "social_stance", "npc_id": "bran", "expected_stance": "cooperative"},
        ],
    },
    "social_save_load_preserves_reputation_and_fear": {
        "setup_social_state": {
            "relationships": {"bran": {"trust": 12, "fear": 8, "reputation": 5}},
            "global_reputation": {"player": 4},
        },
        "turns": ["I ask Bran what he thinks of me after our history."],
        "checks": [
            {"type": "social_relationship", "npc_id": "bran", "expected": {"trust": 12, "fear": 8, "reputation": 5}},
            {"type": "social_global_reputation", "actor_id": "player", "expected": 4},
        ],
    },
}