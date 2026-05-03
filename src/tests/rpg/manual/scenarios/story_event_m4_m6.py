from __future__ import annotations

from typing import Any, Dict


STORY_EVENT_M4_M6_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "story_event_applies_arc_pressure_delta": {
        "setup_story_arc_transitions": [
            {"action": "start", "arc_id": "arc:bandit_pressure", "stage": "rumors", "pressure": 20}
        ],
        "setup_story_events": [
            {
                "event_id": "event:bandit_pressure_rises",
                "arc_id": "arc:bandit_pressure",
                "kind": "pressure",
                "summary": "Bandit activity worsened on the road.",
                "effects": [
                    {"type": "arc_pressure_delta", "arc_id": "arc:bandit_pressure", "delta": 25}
                ],
            }
        ],
        "turns": ["I ignore the worsening bandit pressure."],
        "checks": [
            {"type": "story_event_applied", "event_id": "event:bandit_pressure_rises"},
            {
                "type": "story_event_arc",
                "arc_id": "arc:bandit_pressure",
                "expected": {"pressure": 45},
            },
        ],
    },
    "story_event_reveals_lore": {
        "setup_lore_transitions": [
            {"action": "upsert", "lore_id": "lore:red_sashes", "title": "The Red Sashes", "truth_status": "true"}
        ],
        "setup_story_arc_transitions": [
            {"action": "start", "arc_id": "arc:bandit_pressure", "stage": "rumors"}
        ],
        "setup_story_events": [
            {
                "event_id": "event:reveal_red_sashes",
                "arc_id": "arc:bandit_pressure",
                "kind": "discovery",
                "summary": "The Red Sashes were identified.",
                "effects": [
                    {"type": "lore_reveal", "lore_id": "lore:red_sashes"}
                ],
            }
        ],
        "turns": ["I learn who the bandits are."],
        "checks": [
            {"type": "story_event_applied", "event_id": "event:reveal_red_sashes"},
            {
                "type": "story_event_lore",
                "lore_id": "lore:red_sashes",
                "expected": {"revealed_to_player": True, "truth_status": "true"},
            },
        ],
    },
    "story_event_records_causal_memory": {
        "setup_spatial_graph": "tavern_fixture",
        "setup_story_arc_transitions": [
            {"action": "start", "arc_id": "arc:bandit_pressure", "stage": "rumors"}
        ],
        "setup_story_events": [
            {
                "event_id": "event:player_warns_bran_bandits",
                "arc_id": "arc:bandit_pressure",
                "kind": "warning",
                "location_id": "tavern_common_room",
                "actor_id": "player",
                "target_id": "bran",
                "participants": ["player", "bran"],
                "summary": "The player warned Bran about bandits.",
                "tags": ["bandit", "warning"],
                "effects": [
                    {"type": "memory_event"}
                ],
            }
        ],
        "turns": ["I remind Bran that I warned him."],
        "checks": [
            {
                "type": "story_event_memory",
                "subject_id": "bran",
                "expected_event_id": "event:player_warns_bran_bandits",
                "tags": ["warning"],
            }
        ],
    },
    "story_event_applies_social_delta": {
        "setup_story_arc_transitions": [
            {"action": "start", "arc_id": "arc:bandit_pressure", "stage": "rumors"}
        ],
        "setup_story_events": [
            {
                "event_id": "event:bandits_threaten_bran",
                "arc_id": "arc:bandit_pressure",
                "kind": "threat",
                "summary": "Bandits threatened Bran.",
                "effects": [
                    {"type": "social_delta", "npc_id": "bran", "fear": 10, "trust": -2}
                ],
            }
        ],
        "turns": ["I see Bran react to the threat."],
        "checks": [
            {
                "type": "story_event_social",
                "npc_id": "bran",
                "expected": {"fear": 10, "trust": -2},
            }
        ],
    },
    "story_event_can_trigger_quest_transition": {
        "setup_story_arc_transitions": [
            {"action": "start", "arc_id": "arc:bandit_pressure", "stage": "rumors"}
        ],
        "setup_story_events": [
            {
                "event_id": "event:start_stop_red_sashes",
                "arc_id": "arc:bandit_pressure",
                "kind": "quest_seed",
                "summary": "The bandit problem became a quest.",
                "effects": [
                    {
                        "type": "quest_transition",
                        "transition": {
                            "action": "start",
                            "quest_id": "quest:stop_red_sashes",
                            "stage": "investigate",
                        },
                    }
                ],
            }
        ],
        "turns": ["I accept the need to investigate the Red Sashes."],
        "checks": [
            {
                "type": "story_event_quest",
                "quest_id": "quest:stop_red_sashes",
                "expected": {"stage": "investigate", "status": "active"},
            }
        ],
    },
    "story_event_rejects_unknown_effect_type": {
        "setup_story_arc_transitions": [
            {"action": "start", "arc_id": "arc:bandit_pressure", "stage": "rumors"}
        ],
        "turns": ["I test an invalid story effect."],
        "checks": [
            {
                "type": "story_event_validation",
                "expected_ok": False,
                "event": {
                    "event_id": "event:invalid_effect",
                    "arc_id": "arc:bandit_pressure",
                    "effects": [{"type": "invent_gold", "amount": 999}],
                },
            }
        ],
    },
    "story_event_rejects_missing_arc": {
        "turns": ["I test an event with a missing arc."],
        "checks": [
            {
                "type": "story_event_validation",
                "expected_ok": False,
                "event": {
                    "event_id": "event:missing_arc",
                    "arc_id": "arc:missing",
                    "effects": [],
                },
            }
        ],
    },
    "story_event_rejects_missing_location": {
        "setup_story_arc_transitions": [
            {"action": "start", "arc_id": "arc:bandit_pressure", "stage": "rumors"}
        ],
        "turns": ["I test a location-required event without a location."],
        "checks": [
            {
                "type": "story_event_validation",
                "expected_ok": False,
                "event": {
                    "event_id": "event:missing_location",
                    "arc_id": "arc:bandit_pressure",
                    "require_location": True,
                    "effects": [],
                },
            }
        ],
    },
    "story_event_save_load_records_applied_event_once": {
        "setup_story_arc_transitions": [
            {"action": "start", "arc_id": "arc:bandit_pressure", "stage": "rumors", "pressure": 10}
        ],
        "setup_story_events": [
            {
                "event_id": "event:save_load_once",
                "arc_id": "arc:bandit_pressure",
                "effects": [
                    {"type": "arc_pressure_delta", "arc_id": "arc:bandit_pressure", "delta": 20}
                ],
            },
            {
                "event_id": "event:save_load_once",
                "arc_id": "arc:bandit_pressure",
                "effects": [
                    {"type": "arc_pressure_delta", "arc_id": "arc:bandit_pressure", "delta": 20}
                ],
            },
        ],
        "turns": ["I check that the event applied only once."],
        "checks": [
            {"type": "story_event_applied", "event_id": "event:save_load_once"},
            {
                "type": "story_event_arc",
                "arc_id": "arc:bandit_pressure",
                "expected": {"pressure": 30},
            },
        ],
    },
    "story_event_idempotency_prevents_double_apply": {
        "setup_story_arc_transitions": [
            {"action": "start", "arc_id": "arc:bandit_pressure", "stage": "rumors", "pressure": 15}
        ],
        "setup_story_events": [
            {
                "event_id": "event:idempotent_pressure",
                "arc_id": "arc:bandit_pressure",
                "effects": [
                    {"type": "arc_pressure_delta", "arc_id": "arc:bandit_pressure", "delta": 10}
                ],
            },
            {
                "event_id": "event:idempotent_pressure",
                "arc_id": "arc:bandit_pressure",
                "effects": [
                    {"type": "arc_pressure_delta", "arc_id": "arc:bandit_pressure", "delta": 10}
                ],
            },
        ],
        "turns": ["I check idempotency again."],
        "checks": [
            {
                "type": "story_event_arc",
                "arc_id": "arc:bandit_pressure",
                "expected": {"pressure": 25},
            }
        ],
    },
    "story_event_emits_bounded_world_event": {
        "setup_story_arc_transitions": [
            {"action": "start", "arc_id": "arc:bandit_pressure", "stage": "rumors"}
        ],
        "setup_story_events": [
            {
                "event_id": "event:world_warning",
                "arc_id": "arc:bandit_pressure",
                "kind": "warning",
                "location_id": "tavern_common_room",
                "summary": "Bandits warned Bran.",
                "tags": ["bandit", "warning"],
                "effects": [{"type": "world_event_emit"}],
            }
        ],
        "turns": ["I check the world event log."],
        "checks": [
            {
                "type": "story_event_world_event",
                "source_story_event_id": "event:world_warning",
            }
        ],
    },
}