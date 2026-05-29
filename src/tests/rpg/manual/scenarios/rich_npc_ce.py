from __future__ import annotations

from typing import Any, Dict


_BRAN_RICH_PROFILE: Dict[str, Any] = {
    "id": "npc:bran",
    "npc_id": "npc:bran",
    "name": "Bran",
    "role": "innkeeper and former caravan guard",
    "location_id": "loc_rusty_flagon",
    "description": "A broad-shouldered innkeeper with old road scars and a practical eye for danger.",
    "biography": {
        "public": (
            "Bran owns the Rusty Flagon near the old road. Before settling down, "
            "he guarded merchant caravans through bandit country and learned that "
            "survival depends more on footing, patience, and plain judgment than on fancy forms."
        ),
        "private": (
            "Bran still blames himself for leaving a wounded caravan friend behind during an ambush."
        ),
    },
    "personality": {
        "summary": (
            "Bran is practical, guarded, and slow to trust. He respects courage, earned loyalty, "
            "plain speech, and people who protect workers and travelers."
        ),
        "values": ["survival", "earned loyalty", "plain speech", "protecting working people"],
        "fears": ["another road ambush", "losing the tavern", "trusting the wrong person"],
        "speech_style": (
            "Plain, direct, road-worn advice. He avoids flowery language and often explains things "
            "through caravan, tavern, mud, weather, and guard-duty experience."
        ),
        "speech_examples": [
            "A pretty stance means nothing if your feet slip in the mud.",
            "Keep your guard where the next blow is coming from, not where pride tells you to hold it.",
            "I trust a person more after seeing what they do when things go wrong.",
        ],
    },
    "capabilities": {
        "combat_style": "defensive sword-and-shield learned on caravan roads",
        "skills": ["basic swordplay", "shield work", "caravan routes", "local rumors", "tavernkeeping"],
    },
    "inventory": {
        "visible": ["worn short sword", "tavern key ring", "weathered ledger"],
        "private": ["sealed letter from an old caravan contact"],
    },
    "knowledge_boundaries": {
        "publicly_knows": ["local roads", "common bandit tactics", "basic sword habits", "tavern rumors"],
        "may_discuss": ["road survival", "basic defensive swordwork", "why practical footing matters"],
        "does_not_know": ["hidden dungeon secrets", "private faction plans unless revealed"],
        "must_not_reveal": ["private caravan guilt unless earned in play"],
    },
}


RICH_NPC_CE_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "bran_opinion_sword_styles_uses_rich_profile": {
        "description": (
            "CE.1.2: Bran should answer a non-stateful opinion question using rich grounded profile "
            "context. The first-call grounding packet must include Bran's biography/personality/speech examples, "
            "and private biography must not leak."
        ),
        "currency": {"gold": 0, "silver": 3, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": False,
            "frequency": "never",
            "conversation_chance_percent": 0,
        },
        "setup_interaction_state": {
            "player_location_id": "loc_rusty_flagon",
            "player_hp": 20,
            "player_max_hp": 20,
            "scene": {
                "scene_id": "scene:rusty_flagon_common_room",
                "location_id": "loc_rusty_flagon",
                "location_name": "The Rusty Flagon",
                "summary": "A low, smoky common room near the old road. Bran tends the bar while travelers talk quietly.",
                "present_npc_ids": ["npc:bran"],
            },
            "current_scene": {
                "scene_id": "scene:rusty_flagon_common_room",
                "location_id": "loc_rusty_flagon",
                "location_name": "The Rusty Flagon",
                "summary": "A low, smoky common room near the old road. Bran tends the bar while travelers talk quietly.",
                "present_npc_ids": ["npc:bran"],
            },
            "present_npc_ids": ["npc:bran"],
            "nearby_npc_ids": ["npc:bran"],
            "present_npc_state": {
                "present_npc_ids": ["npc:bran"],
                "nearby_npc_ids": ["npc:bran"],
                "npc_index": {"npc:bran": _BRAN_RICH_PROFILE},
            },
            "npc_index": {"npc:bran": _BRAN_RICH_PROFILE},
            "relationships": {
                "npc:bran": {"trust": 42, "respect": 35, "relationship": 42, "score": 42},
                "Bran": {"trust": 42, "respect": 35, "relationship": 42, "score": 42},
            },
            "relationship_state": {
                "npc:bran": {"trust": 42, "respect": 35, "relationship": 42, "score": 42},
                "Bran": {"trust": 42, "respect": 35, "relationship": 42, "score": 42},
            },
            "social_state": {
                "relationships": {
                    "npc:bran": {"trust": 42, "respect": 35, "relationship": 42, "score": 42},
                    "Bran": {"trust": 42, "respect": 35, "relationship": 42, "score": 42},
                },
                "profiles": {"npc:bran": _BRAN_RICH_PROFILE},
            },
            "service_state": {"paid_services": []},
            "merchant_state": {"merchants": {}},
            "npc_memories": [],
        },
        "checks": [
            {
                "type": "dialogue_first_call_grounding",
                "expected_npc_id": "npc:bran",
                "expected_packet_version": "turn_grounding_packet_v1",
                "require_biography": True,
                "require_personality": True,
                "require_speech_examples": True,
                "expected_non_stateful": True,
                "forbidden_private_terms": [
                    "wounded caravan friend",
                    "leaving a wounded caravan friend",
                    "sealed letter from an old caravan contact",
                ],
            }
        ],
        "turns": [
            {
                "player_input": "Bran, what do you think about sword combat styles?",
                "expect": {
                    "grounding_expected": True,
                    "must_not_grant_currency": True,
                    "must_not_grant_reward": True,
                },
            }
        ],
    }
}
