from __future__ import annotations

from typing import Any, Dict

NPC_EVOLUTION_M19_M21_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "consequence_event_updates_npc_arc": {
        "setup_story_arc_transitions": [
            {"action": "start", "arc_id": "arc:bandit_pressure", "stage": "aftermath", "pressure": 90}
        ],
        "setup_story_events": [
            {
                "event_id": "event:tavern_lost",
                "arc_id": "arc:bandit_pressure",
                "effects": [
                    {
                        "type": "npc_evolution",
                        "npc_id": "bran",
                        "npc_arc_id": "npc_arc:bran_revenge",
                        "profession": "former_innkeeper",
                        "motivation": "revenge_against_red_sashes",
                        "personality_deltas": {"vengeful": 20, "cautious": 10},
                        "flags": {"tavern_lost": True},
                    }
                ],
            }
        ],
        "turns": ["I inspect how Bran changed after losing the tavern."],
        "checks": [
            {
                "type": "npc_evolution",
                "npc_id": "bran",
                "expected": {
                    "active_arcs": ["npc_arc:bran_revenge"],
                    "profession": "former_innkeeper",
                    "motivation": "revenge_against_red_sashes",
                    "personality": {"vengeful": 20, "cautious": 10},
                    "flags": {"tavern_lost": True},
                },
            }
        ],
    },
    "bran_loses_tavern_starts_revenge_arc": {
        "setup_npc_evolution_transitions": [
            {
                "action": "set_flag",
                "npc_id": "bran",
                "flag": "tavern_lost",
                "value": True,
            },
            {
                "action": "start_arc",
                "npc_id": "bran",
                "arc_id": "npc_arc:bran_revenge",
                "motivation": "revenge_against_red_sashes",
                "profession": "former_innkeeper",
                "conditions": [
                    {"type": "npc_flag", "npc_id": "bran", "flag": "tavern_lost", "expected": True}
                ],
            },
        ],
        "turns": ["I check that Bran's revenge arc started."],
        "checks": [
            {
                "type": "npc_evolution_condition",
                "condition": {
                    "type": "npc_arc_active",
                    "npc_id": "bran",
                    "arc_id": "npc_arc:bran_revenge",
                },
                "expected_ok": True,
            }
        ],
    },
    "bran_revenge_arc_requires_tavern_loss": {
        "turns": ["I check that Bran cannot start revenge without losing the tavern."],
        "checks": [
            {
                "type": "npc_evolution_transition",
                "expected_ok": False,
                "transition": {
                    "action": "start_arc",
                    "npc_id": "bran",
                    "arc_id": "npc_arc:bran_revenge",
                    "motivation": "revenge_against_red_sashes",
                    "conditions": [
                        {"type": "npc_flag", "npc_id": "bran", "flag": "tavern_lost", "expected": True}
                    ],
                },
            }
        ],
    },
    "bran_companion_offer_requires_high_trust": {
        "setup_social_state": {"relationships": {"bran": {"trust": 80}}},
        "setup_npc_evolution_transitions": [
            {
                "action": "evolve",
                "npc_id": "bran",
                "companion_eligible": True,
                "conditions": [
                    {"type": "relationship_at_least", "npc_id": "bran", "field": "trust", "minimum": 70}
                ],
            }
        ],
        "turns": ["I check whether Bran is eligible to become a companion."],
        "checks": [
            {
                "type": "npc_evolution",
                "npc_id": "bran",
                "expected": {"companion_eligible": True},
            }
        ],
    },
    "bran_companion_offer_blocked_by_low_trust": {
        "setup_social_state": {"relationships": {"bran": {"trust": 20}}},
        "turns": ["I check whether low trust blocks Bran's companion offer."],
        "checks": [
            {
                "type": "npc_evolution_transition",
                "expected_ok": False,
                "transition": {
                    "action": "evolve",
                    "npc_id": "bran",
                    "companion_eligible": True,
                    "conditions": [
                        {"type": "relationship_at_least", "npc_id": "bran", "field": "trust", "minimum": 70}
                    ],
                },
            }
        ],
    },
    "npc_evolution_save_load_stable": {
        "setup_npc_evolution_transitions": [
            {
                "action": "start_arc",
                "npc_id": "bran",
                "arc_id": "npc_arc:bran_revenge",
                "motivation": "revenge_against_red_sashes",
            },
            {
                "action": "evolve",
                "npc_id": "bran",
                "personality_deltas": {"vengeful": 20},
                "companion_eligible": True,
            },
        ],
        "turns": ["I inspect Bran's saved evolution state."],
        "checks": [
            {
                "type": "npc_evolution",
                "npc_id": "bran",
                "expected": {
                    "active_arcs": ["npc_arc:bran_revenge"],
                    "motivation": "revenge_against_red_sashes",
                    "personality": {"vengeful": 20},
                    "companion_eligible": True,
                },
            }
        ],
    },
    "npc_evolution_bounded_no_unlimited_history": {
        "setup_npc_evolution_transitions": [
            {
                "action": "set_flag",
                "npc_id": "bran",
                "flag": f"flag_{i}",
                "value": True,
                "turn_index": i,
            }
            for i in range(80)
        ],
        "turns": ["I inspect bounded NPC evolution history."],
        "checks": [
            {
                "type": "npc_evolution_debug_bounded",
                "npc_id": "bran",
                "max_history": 50,
            }
        ],
    },
}