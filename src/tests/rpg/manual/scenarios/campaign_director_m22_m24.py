from __future__ import annotations

from typing import Any, Dict


def _director_pack() -> Dict[str, Any]:
    return {
        "proposal_version": "story_proposal_v1",
        "proposal_type": "story_pack",
        "proposal_id": "director_bandit_pack",
        "title": "Director Bandit Pack",
        "lore_entries": [
            {
                "lore_id": "lore:red_sashes",
                "title": "The Red Sashes",
                "truth_status": "rumor",
            }
        ],
        "story_arcs": [
            {
                "arc_id": "arc:bandit_pressure",
                "title": "Bandit Pressure",
                "status": "active",
                "stage": "rumors",
                "pressure": 60,
                "linked_lore": ["lore:red_sashes"],
                "linked_entities": ["bran"],
            }
        ],
        "story_events": [
            {
                "event_id": "event:bandits_burn_tavern",
                "arc_id": "arc:bandit_pressure",
                "kind": "consequence",
                "summary": "Bandits burned Bran's tavern.",
                "effects": [
                    {"type": "arc_stage_set", "arc_id": "arc:bandit_pressure", "stage": "aftermath"},
                    {
                        "type": "npc_evolution",
                        "npc_id": "bran",
                        "npc_arc_id": "npc_arc:bran_revenge",
                        "profession": "former_innkeeper",
                        "motivation": "revenge_against_red_sashes",
                        "personality_deltas": {"vengeful": 20},
                        "flags": {"tavern_lost": True},
                    },
                    {"type": "world_event_emit"},
                ],
            }
        ],
        "escalation_rules": [
            {
                "rule_id": "rule:burn_tavern",
                "arc_id": "arc:bandit_pressure",
                "priority": 90,
                "conditions": [
                    {
                        "type": "arc_pressure_at_least",
                        "arc_id": "arc:bandit_pressure",
                        "minimum": 50,
                    },
                    {
                        "type": "arc_stage",
                        "arc_id": "arc:bandit_pressure",
                        "stage": "rumors",
                    },
                ],
                "event": {
                    "event_id": "event:bandits_burn_tavern",
                    "arc_id": "arc:bandit_pressure",
                    "effects": [],
                },
                "cooldown_turns": 5,
                "max_applications": 1,
            }
        ],
    }


CAMPAIGN_DIRECTOR_M22_M24_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "campaign_director_evaluates_story_pack_rules": {
        "setup_story_packs": [{"proposal": _director_pack(), "turn_index": 1}],
        "turns": ["I wait and let the campaign director inspect the world."],
        "checks": [
            {
                "type": "campaign_director_evaluate",
                "mode": "idle",
                "turn_index": 2,
                "expected_eligible_count": 1,
                "expected_first_event_id": "event:bandits_burn_tavern",
            },
            {
                "type": "campaign_director_arc",
                "arc_id": "arc:bandit_pressure",
                "expected": {"stage": "rumors"},
            },
        ],
    },
    "campaign_director_applies_registered_escalation_event": {
        "setup_story_packs": [{"proposal": _director_pack(), "turn_index": 1}],
        "setup_campaign_director_ticks": [{"mode": "idle", "turn_index": 2}],
        "turns": ["I inspect the director-applied consequence."],
        "checks": [
            {
                "type": "campaign_director_event_applied",
                "event_id": "event:bandits_burn_tavern",
            },
            {
                "type": "campaign_director_arc",
                "arc_id": "arc:bandit_pressure",
                "expected": {"stage": "aftermath"},
            },
            {
                "type": "campaign_director_npc_evolution",
                "npc_id": "bran",
                "expected": {
                    "active_arcs": ["npc_arc:bran_revenge"],
                    "profession": "former_innkeeper",
                    "motivation": "revenge_against_red_sashes",
                    "personality": {"vengeful": 20},
                    "flags": {"tavern_lost": True},
                },
            },
        ],
    },
    "campaign_director_does_not_apply_in_combat_mode": {
        "setup_story_packs": [{"proposal": _director_pack(), "turn_index": 1}],
        "turns": ["I check that combat mode blocks campaign escalation."],
        "checks": [
            {
                "type": "campaign_director_apply",
                "mode": "combat",
                "turn_index": 2,
                "expected_applied_count": 0,
                "expected_reason": "unsafe_mode",
            },
            {
                "type": "campaign_director_arc",
                "arc_id": "arc:bandit_pressure",
                "expected": {"stage": "rumors"},
            },
        ],
    },
    "campaign_director_respects_max_applications": {
        "setup_story_packs": [{"proposal": _director_pack(), "turn_index": 1}],
        "setup_campaign_director_ticks": [
            {"mode": "idle", "turn_index": 2},
            {"mode": "idle", "turn_index": 3},
        ],
        "turns": ["I check that the campaign consequence only applied once."],
        "checks": [
            {
                "type": "campaign_director_arc",
                "arc_id": "arc:bandit_pressure",
                "expected": {"stage": "aftermath"},
            },
            {
                "type": "campaign_director_event_applied",
                "event_id": "event:bandits_burn_tavern",
            },
            {
                "type": "campaign_director_apply",
                "mode": "idle",
                "turn_index": 4,
                "expected_applied_count": 0,
            },
        ],
    },
    "campaign_director_ignores_resolved_arc": {
        "setup_story_packs": [
            {
                "proposal": dict(
                    _director_pack(),
                    story_arcs=[
                        dict(
                            _director_pack()["story_arcs"][0],
                            status="resolved",
                            stage="resolved",
                        )
                    ],
                ),
                "turn_index": 1,
            }
        ],
        "turns": ["I check that resolved arcs do not escalate."],
        "checks": [
            {
                "type": "campaign_director_evaluate",
                "mode": "idle",
                "turn_index": 2,
                "expected_eligible_count": 0,
            }
        ],
    },
    "campaign_director_snapshot_is_bounded": {
        "setup_story_packs": [{"proposal": _director_pack(), "turn_index": 1}],
        "turns": ["I inspect the bounded campaign director snapshot."],
        "checks": [
            {
                "type": "campaign_director_snapshot",
                "mode": "idle",
                "turn_index": 2,
                "expected_advisory_only": True,
                "max_pressure_items": 10,
            }
        ],
    },
    "campaign_director_no_story_pack_rules_noops": {
        "turns": ["I wait with no imported story pack rules."],
        "checks": [
            {
                "type": "campaign_director_evaluate",
                "mode": "idle",
                "turn_index": 2,
                "expected_eligible_count": 0,
            },
            {
                "type": "campaign_director_apply",
                "mode": "idle",
                "turn_index": 3,
                "expected_applied_count": 0,
            },
        ],
    },
}