from __future__ import annotations

from typing import Any, Dict

CONVERSATION_CORE_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "ambient_conversation": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "turns": [
            "I wait and listen to the room",
            "I wait and listen a little longer",
        ],
    },
    "autonomous_conversation": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
            "max_world_signals_per_thread": 4,
        },
        "turns": [
            "__ambient_tick__",
            "__ambient_tick__",
            "__ambient_tick__",
        ],
    },
    "conversation_discusses_event": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_event_discussion": True,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
        },
        "setup_world_events": [
            {
                "event_id": "manual:event:old_mill_traveler",
                "kind": "travel",
                "title": "A traveler arrived from the old mill road",
                "summary": "A nervous traveler came from the old mill road.",
                "location_id": "loc_tavern",
                "source": "manual_scenario_setup"
            }
        ],
        "turns": ["__ambient_tick_event__"],
    },
    "conversation_discusses_quest": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_quest_discussion": True,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
        },
        "setup_quest_state": {
            "quests": [
                {
                    "quest_id": "quest:old_mill_bandits",
                    "title": "Trouble near the Old Mill",
                    "summary": "There is talk of armed figures near the old mill road.",
                    "status": "active",
                    "location_id": "loc_tavern"
                }
            ]
        },
        "turns": ["__ambient_tick_quest__"],
    },
    "player_invited_conversation": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": True,
            "player_inclusion_chance_percent": 100,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
        },
        "turns": [
            "__ambient_tick_player_invited__",
            "What do you mean about the old mill?",
        ],
    },
    "npc_replies_after_player_join": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": True,
            "player_inclusion_chance_percent": 100,
            "allow_npc_response_beats": True,
            "npc_response_style_influence": True,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
        },
        "turns": [
            "__ambient_tick_player_invited__",
            "I hear you. Tell me more about what is happening around here.",
        ],
    },
    "player_requests_backed_quest_topic": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": True,
            "player_inclusion_chance_percent": 100,
            "allow_npc_response_beats": True,
            "npc_response_style_influence": True,
            "allow_quest_discussion": True,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
        },
        "setup_quest_state": {
            "quests": [
                {
                    "quest_id": "quest:old_mill_bandits",
                    "title": "Trouble near the Old Mill",
                    "summary": "There is talk of armed figures near the old mill road at night.",
                    "status": "active",
                    "location_id": "loc_tavern",
                }
            ]
        },
        "turns": [
            "__ambient_tick_player_invited__",
            "What can you tell me about the trouble at the old mill road?",
        ],
    },
    "player_requests_unbacked_topic": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": True,
            "player_inclusion_chance_percent": 100,
            "allow_npc_response_beats": True,
            "npc_response_style_influence": True,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
        },
        "turns": [
            "__ambient_tick_player_invited__",
            "Tell me about the dragon lair hidden in the northern mountains.",
        ],
    },
    "npc_response_uses_social_state": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": True,
            "player_inclusion_chance_percent": 100,
            "allow_npc_response_beats": True,
            "npc_response_style_influence": True,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
        },
        "turns": [
            "__ambient_tick_player_invited__",
            "I am happy to chat with you. What is on your mind?",
            "__ambient_tick_player_invited__",
            "Yes, I would love to hear more. You seem like someone worth talking to.",
        ],
    },
    "rumor_seed_from_conversation": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_quest_discussion": True,
            "allow_rumor_propagation": True,
            "max_rumor_seeds": 16,
            "max_rumor_mentions_per_location": 4,
            "max_signal_age_ticks": 20,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
            "max_world_signals_per_thread": 4,
        },
        "setup_quest_state": {
            "quests": [
                {
                    "quest_id": "quest:old_mill_bandits",
                    "title": "Trouble near the Old Mill",
                    "summary": "There is talk of armed figures near the old mill road at night.",
                    "status": "active",
                    "location_id": "loc_tavern",
                }
            ]
        },
        "turns": [
            "__ambient_tick_quest__",
            "__ambient_tick__",
            "__ambient_tick__",
        ],
    },
    "rumor_signal_expires": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_quest_discussion": True,
            "allow_rumor_propagation": True,
            "max_rumor_seeds": 16,
            "max_rumor_mentions_per_location": 4,
            "max_signal_age_ticks": 3,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
            "max_world_signals_per_thread": 4,
        },
        "setup_quest_state": {
            "quests": [
                {
                    "quest_id": "quest:old_mill_bandits",
                    "title": "Trouble near the Old Mill",
                    "summary": "There is talk of armed figures near the old mill road at night.",
                    "status": "active",
                    "location_id": "loc_tavern",
                }
            ]
        },
        "turns": [
            "__ambient_tick_quest__",   # turn 1 — seeds the rumor (expires_tick = 1 + 3 = 4)
            "__ambient_tick__",          # turn 2 — seed still active
            "__ambient_tick__",          # turn 3 — seed at expiry boundary
            "__ambient_tick__",          # turn 4 — seed should be gone (expired)
            "__ambient_tick__",          # turn 5 — confirm no stale seed re-seeded
        ],
    },
    "npc_npc_multiturn_conversation": {
        "currency": {
            "gold": 0,
            "silver": 0,
            "copper": 0
        },
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": False,
            "allow_event_discussion": True,
            "allow_quest_discussion": True,
            "allow_npc_response_beats": True,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
            "max_world_signals_per_thread": 4,
            "max_world_events_per_thread": 4
        },
        "setup_world_events": [
            {
                "event_id": "manual:event:mill_road_traveler",
                "kind": "travel",
                "title": "A traveler arrived from the old mill road",
                "summary": "A nervous traveler arrived at the Rusty Flagon Tavern from the old mill road, speaking of strange lights seen near the mill at dusk and the sound of armed men.",
                "location_id": "loc_tavern",
                "source": "manual_scenario_setup"
            }
        ],
        "turns": [
            "__ambient_tick__",
            "__ambient_tick__",
            "__ambient_tick__",
            "__ambient_tick__"
        ]
    },
    "npc_npc_multiturn_quest_discussion": {
        "currency": {
            "gold": 0,
            "silver": 0,
            "copper": 0
        },
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": False,
            "allow_quest_discussion": True,
            "allow_npc_response_beats": True,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
            "max_world_signals_per_thread": 4,
            "max_world_events_per_thread": 4
        },
        "setup_quest_state": {
            "quests": [
                {
                    "quest_id": "quest:old_mill_bandits",
                    "title": "Trouble near the Old Mill",
                    "summary": "There is talk of armed figures gathering near the old mill road at night. Locals are nervous and trade caravans have avoided the route.",
                    "status": "active",
                    "location_id": "loc_tavern"
                }
            ]
        },
        "turns": [
            "__ambient_tick_quest__",
            "__ambient_tick__",
            "__ambient_tick__",
            "__ambient_tick__"
        ]
    },
}
