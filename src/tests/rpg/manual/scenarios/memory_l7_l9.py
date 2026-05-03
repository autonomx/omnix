from __future__ import annotations

from typing import Any, Dict


MEMORY_L7_L9_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "memory_npc_remembers_same_room_event": {
        "setup_spatial_graph": "tavern_fixture",
        "setup_memory_events": ["same_room_greeting"],
        "turns": ["I ask Bran if he remembers me greeting him."],
        "checks": [
            {
                "type": "memory_retrieval",
                "subject_id": "bran",
                "actor_id": "player",
                "tags": ["greeting"],
                "expected_event_ids": ["evt:manual_same_room_greeting"],
            }
        ],
    },
    "memory_npc_does_not_remember_unseen_private_room_event": {
        "setup_spatial_graph": "tavern_fixture",
        "setup_memory_events": ["private_room_quiet_event"],
        "turns": ["I ask Bran about the quiet private-room exchange."],
        "checks": [
            {
                "type": "memory_retrieval",
                "subject_id": "bran",
                "tags": ["private"],
                "forbidden_event_ids": ["evt:manual_private_room_quiet_event"],
            }
        ],
    },
    "memory_npc_hears_muffled_event_through_closed_door": {
        "setup_spatial_graph": "tavern_fixture",
        "setup_memory_events": ["private_room_argument"],
        "turns": ["I ask Bran if he heard the argument in the private room."],
        "checks": [
            {
                "type": "memory_retrieval",
                "subject_id": "bran",
                "tags": ["argument"],
                "expected_event_ids": ["evt:manual_private_room_argument"],
            }
        ],
    },
    "memory_hidden_npc_not_observed_by_player": {
        "setup_spatial_graph": "tavern_fixture_private_door_open",
        "setup_memory_events": ["private_room_quiet_event"],
        "turns": ["I ask what I noticed in the private room."],
        "checks": [
            {
                "type": "memory_retrieval",
                "subject_id": "player",
                "target_id": "spy",
                "forbidden_event_ids": ["evt:manual_private_room_quiet_event"],
            }
        ],
    },
    "memory_told_event_becomes_known": {
        "setup_spatial_graph": "tavern_fixture",
        "setup_told_memories": [
            {
                "subject_id": "bran",
                "speaker_id": "player",
                "event_id": "evt:manual_told_bandits",
                "summary": "The player told Bran that bandits were on the road.",
                "facts": {
                    "actor_id": "bandits",
                    "location_id": "road",
                    "action": "reported",
                },
                "confidence": 0.7,
                "tags": ["bandit"],
                "verified": False,
            }
        ],
        "turns": ["I ask Bran what I told him about bandits."],
        "checks": [
            {
                "type": "memory_retrieval",
                "subject_id": "bran",
                "tags": ["bandit", "claim"],
                "expected_event_ids": ["evt:manual_told_bandits"],
            }
        ],
    },
    "memory_unbacked_claim_not_promoted_to_fact": {
        "setup_spatial_graph": "tavern_fixture",
        "setup_told_memories": [
            {
                "subject_id": "bran",
                "speaker_id": "player",
                "event_id": "evt:manual_unbacked_dragon_claim",
                "summary": "The player claimed a dragon owned the tavern.",
                "facts": {
                    "actor_id": "player",
                    "target_id": "dragon",
                    "action": "claimed",
                },
                "confidence": 0.4,
                "tags": ["dragon"],
                "verified": False,
            }
        ],
        "turns": ["I ask Bran if the dragon claim is proven fact."],
        "checks": [
            {
                "type": "memory_retrieval",
                "subject_id": "bran",
                "tags": ["claim", "unverified"],
                "expected_event_ids": ["evt:manual_unbacked_dragon_claim"],
            }
        ],
    },
    "memory_directly_affected_npc_remembers": {
        "setup_spatial_graph": "tavern_fixture",
        "setup_memory_events": ["player_affects_bran"],
        "turns": ["I ask Bran whether he remembers the insult."],
        "checks": [
            {
                "type": "memory_retrieval",
                "subject_id": "bran",
                "tags": ["insult"],
                "expected_event_ids": ["evt:manual_player_affects_bran"],
            }
        ],
    },
    "memory_retrieval_bounded_to_recent_relevant_items": {
        "setup_spatial_graph": "tavern_fixture",
        "setup_memory_events": [
            "same_room_greeting",
            "private_room_argument",
            "player_affects_bran",
            "street_bandit_seen",
        ],
        "turns": ["I ask Bran for the most relevant recent memories about me."],
        "checks": [
            {
                "type": "memory_retrieval",
                "subject_id": "bran",
                "actor_id": "player",
                "max_items": 3,
                "expected_event_ids": ["evt:manual_player_affects_bran"],
            },
            {
                "type": "memory_count_max",
                "subject_id": "bran",
                "max_expected": 100,
            },
        ],
    },
    "memory_spatial_visibility_filters_observers": {
        "setup_spatial_graph": "tavern_fixture",
        "setup_memory_events": ["private_room_quiet_event"],
        "turns": ["I check whether visibility filtered observers."],
        "checks": [
            {
                "type": "memory_retrieval",
                "subject_id": "bran",
                "tags": ["quiet"],
                "forbidden_event_ids": ["evt:manual_private_room_quiet_event"],
            }
        ],
    },
    "memory_spatial_audibility_filters_hearers": {
        "setup_spatial_graph": "tavern_fixture",
        "setup_memory_events": ["private_room_argument"],
        "turns": ["I check whether audibility created a heard memory."],
        "checks": [
            {
                "type": "memory_retrieval",
                "subject_id": "bran",
                "tags": ["muffled"],
                "expected_event_ids": ["evt:manual_private_room_argument"],
            }
        ],
    },
    "memory_save_load_preserves_causal_memory": {
        "setup_spatial_graph": "tavern_fixture",
        "setup_memory_events": ["same_room_greeting"],
        "turns": ["I ask Bran about the saved greeting memory."],
        "checks": [
            {
                "type": "memory_retrieval",
                "subject_id": "bran",
                "tags": ["greeting"],
                "expected_event_ids": ["evt:manual_same_room_greeting"],
            }
        ],
    },
    "memory_npc_dialogue_uses_retrieved_fact_not_global_state": {
        "setup_spatial_graph": "tavern_fixture",
        "setup_memory_events": ["same_room_greeting"],
        "turns": ["I ask Bran what he personally remembers seeing."],
        "checks": [
            {
                "type": "memory_retrieval",
                "subject_id": "bran",
                "actor_id": "player",
                "expected_event_ids": ["evt:manual_same_room_greeting"],
                "forbidden_event_ids": ["evt:manual_private_room_quiet_event"],
            }
        ],
    },
}