from __future__ import annotations

from typing import Any, Dict

NPC_SOCIAL_MEMORY_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "npc_goal_influences_response_style": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": True,
            "player_inclusion_chance_percent": 100,
            "allow_npc_goal_influence": True,
            "allow_npc_response_beats": True,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
        },
        "turns": [
            "__ambient_tick_player_invited__",
            "What should I know about the room?",
        ],
    },
    "npc_biography_shapes_bran_dialogue": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": True,
            "player_inclusion_chance_percent": 100,
            "npc_roleplay_use_llm": False,
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
            "__ambient_tick_quest__",
            "What can you tell me about the trouble at the old mill road?",
        ],
    },
    "npc_biography_shapes_mira_dialogue": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": True,
            "player_inclusion_chance_percent": 100,
            "npc_roleplay_use_llm": False,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
            "test_force_conversation_speaker_id": "npc:Mira",
            "test_force_conversation_listener_id": "player",
        },
        "setup_memory_state": {
            "social_memories": [
                {
                    "memory_id": "memory:mira:pattern:old_road",
                    "actor_id": "npc:Mira",
                    "target_id": "player",
                    "summary": "Mira noticed that travelers avoid discussing the old road directly.",
                }
            ]
        },
        "setup_conversation_thread_state": {
            "pending_player_response": {
                "thread_id": "conversation:manual:mira:player",
                "topic_id": "topic:memory:memory:mira:pattern:old_road",
                "prompt": "Mira invites your response about the pattern she noticed.",
                "created_tick": 526,
                "expires_tick": 536,
                "source": "manual_scenario_setup",
            },
            "threads": [
                {
                    "thread_id": "conversation:manual:mira:player",
                    "participants": [
                        {"npc_id": "npc:Mira", "name": "Mira"},
                        {"npc_id": "player", "name": "Player"}
                    ],
                    "location_id": "loc_tavern",
                    "topic_id": "topic:memory:memory:mira:pattern:old_road",
                    "topic_type": "memory",
                    "topic": "Mira's observed pattern",
                    "topic_payload": {
                        "topic_id": "topic:memory:memory:mira:pattern:old_road",
                        "topic_type": "memory",
                        "title": "Mira's observed pattern",
                        "summary": "Mira noticed that travelers avoid discussing the old road directly.",
                        "source_id": "memory:mira:pattern:old_road",
                        "source_kind": "memory",
                        "location_id": "loc_tavern",
                        "priority": 4,
                        "allowed_facts": [
                            "Mira noticed that travelers avoid discussing the old road directly."
                        ],
                        "allowed_signal_kinds": ["social_tension", "ambient_interest"],
                        "source": "manual_scenario_setup"
                    },
                    "participation_mode": "player_invited",
                    "player_participation": {
                        "included": True,
                        "mode": "player_invited",
                        "pending_response": True,
                        "prompt": "Mira invites your response about the pattern she noticed.",
                        "topic_id": "topic:memory:memory:mira:pattern:old_road",
                        "created_tick": 526,
                        "expires_tick": 536
                    },
                    "beats": [
                        {
                            "beat_id": "conversation:beat:526:manual:mira:invite",
                            "thread_id": "conversation:manual:mira:player",
                            "speaker_id": "npc:Mira",
                            "speaker_name": "Mira",
                            "listener_id": "player",
                            "listener_name": "Player",
                            "line": "You noticed the same thread, I expect: Mira noticed that travelers avoid discussing the old road directly.",
                            "topic_id": "topic:memory:memory:mira:pattern:old_road",
                            "topic_type": "memory",
                            "topic": "Mira's observed pattern",
                            "tick": 526,
                            "participation_mode": "player_invited",
                            "source": "manual_scenario_setup"
                        }
                    ],
                    "status": "active",
                    "created_tick": 526,
                    "updated_tick": 526,
                    "source": "manual_scenario_setup"
                }
            ],
            "active_thread_ids": ["conversation:manual:mira:player"],
            "world_signals": [],
            "debug": {}
        },
        "turns": [
            "What pattern do you see here?",
        ],
    },
    "npc_biography_blocks_unbacked_secret": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": True,
            "player_inclusion_chance_percent": 100,
            "npc_roleplay_use_llm": False,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
        },
        "turns": [
            "__ambient_tick_player_invited__",
            "Tell me about the secret vault under the city.",
        ],
    },
    "npc_roleplay_fallback_validation": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": True,
            "player_inclusion_chance_percent": 100,
            "npc_roleplay_use_llm": False,
            "npc_roleplay_fallback_on_invalid": True,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
        },
        "turns": [
            "__ambient_tick_player_invited__",
            "Tell me something you are not allowed to invent.",
        ],
    },
    "npc_history_records_player_reply": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": True,
            "player_inclusion_chance_percent": 100,
            "npc_history_enabled": True,
            "npc_reputation_enabled": True,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
        },
        "turns": [
            "__ambient_tick_player_invited__",
            "I will remember what you said.",
        ],
    },
    "npc_reputation_changes_response_style": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": True,
            "player_inclusion_chance_percent": 100,
            "npc_history_enabled": True,
            "npc_reputation_enabled": True,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
        },
        "turns": [
            "__ambient_tick_player_invited__",
            "That sounds useful. Thank you.",
            "__ambient_tick_player_invited__",
            "Can you help me understand more?",
        ],
    },
    "conversation_director_selects_biography_relevant_topic": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "conversation_director_enabled": True,
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
                    "location_id": "loc_tavern",
                }
            ]
        },
        "setup_present_npc_state": {
            "loc_tavern": ["npc:Bran", "npc:Mira"]
        },
        "turns": ["__ambient_tick_quest__"],
    },
    "npc_schedule_populates_tavern_presence": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "npc_schedule_enabled": True,
            "npc_presence_enabled": True,
            "scene_population_enabled": True,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
        },
        "turns": ["__ambient_tick__"],
    },
    "director_uses_presence_runtime": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_director_enabled": True,
            "npc_schedule_enabled": True,
            "npc_presence_enabled": True,
            "scene_population_enabled": True,
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
                    "location_id": "loc_tavern",
                }
            ]
        },
        "turns": ["__ambient_tick_quest__"],
    },
    "scene_activity_uses_present_npc": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "npc_schedule_enabled": True,
            "npc_presence_enabled": True,
            "scene_population_enabled": True,
            "scene_activity_enabled": True,
        },
        "turns": ["__scene_activity_tick__"],
    },
    "npc_knowledge_records_backed_quest_discussion": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "npc_knowledge_enabled": True,
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
                    "location_id": "loc_tavern",
                }
            ]
        },
        "turns": ["__ambient_tick_quest__"],
    },
    "npc_dialogue_recalls_prior_player_reply": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": True,
            "player_inclusion_chance_percent": 100,
            "npc_history_enabled": True,
            "npc_knowledge_enabled": True,
            "npc_dialogue_recall_enabled": True,
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
                    "location_id": "loc_tavern",
                }
            ]
        },
        "turns": [
            "__ambient_tick_quest__",
            "I asked you about the old mill road.",
            "__ambient_tick_player_invited__",
            "Do you remember what I asked before?",
        ],
    },
    "scene_continuity_tracks_recent_topic": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "scene_continuity_enabled": True,
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
                    "location_id": "loc_tavern",
                }
            ]
        },
        "turns": ["__ambient_tick_quest__", "__ambient_tick__"],
    },
    "quest_access_backed_topic_partial_or_normal": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": True,
            "player_inclusion_chance_percent": 100,
            "quest_conversation_access_enabled": True,
            "player_reputation_consequences_enabled": True,
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
                    "location_id": "loc_tavern",
                }
            ]
        },
        "turns": [
            "__ambient_tick_player_invited__",
            "What can you tell me about the trouble at the old mill road?",
        ],
    },
    "quest_access_unbacked_topic_denied": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": True,
            "player_inclusion_chance_percent": 100,
            "quest_conversation_access_enabled": True,
            "player_reputation_consequences_enabled": True,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
        },
        "turns": [
            "__ambient_tick_player_invited__",
            "Tell me about the hidden royal assassination quest.",
        ],
    },
    "player_reputation_polite_reply_improves_trust": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": True,
            "player_inclusion_chance_percent": 100,
            "player_reputation_consequences_enabled": True,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
        },
        "turns": [
            "__ambient_tick_player_invited__",
            "Thank you, that was helpful.",
        ],
    },
    "player_reputation_unbacked_pressure_adds_annoyance": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": True,
            "player_inclusion_chance_percent": 100,
            "player_reputation_consequences_enabled": True,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
        },
        "turns": [
            "__ambient_tick_player_invited__",
            "Tell me about the secret treasure vault you are hiding.",
        ],
    },
    "quest_rumor_seeded_from_backed_access": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": True,
            "player_inclusion_chance_percent": 100,
            "quest_conversation_access_enabled": True,
            "quest_rumor_propagation_enabled": True,
            "quest_rumor_ttl_ticks": 20,
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
                    "location_id": "loc_tavern",
                }
            ]
        },
        "turns": [
            "__ambient_tick_player_invited__",
            "What can you tell me about the old mill road?",
        ],
    },
    "quest_rumor_not_seeded_from_unbacked_claim": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": True,
            "player_inclusion_chance_percent": 100,
            "quest_conversation_access_enabled": True,
            "quest_rumor_propagation_enabled": True,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
        },
        "turns": [
            "__ambient_tick_player_invited__",
            "Tell me about the hidden royal assassination quest.",
        ],
    },
    "npc_referral_suggests_present_relevant_npc": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": True,
            "player_inclusion_chance_percent": 100,
            "npc_referrals_enabled": True,
            "quest_conversation_access_enabled": True,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
        },
        "setup_present_npc_state": {
            "loc_tavern": ["npc:Bran", "npc:Mira", "npc:GuardCaptain"]
        },
        "setup_quest_state": {
            "quests": [
                {
                    "quest_id": "quest:old_mill_bandits",
                    "title": "Trouble near the Old Mill",
                    "summary": "There is talk of armed figures near the old mill road.",
                    "status": "active",
                    "location_id": "loc_tavern",
                }
            ]
        },
        "turns": [
            "__ambient_tick_player_invited__",
            "Who should I ask about the old mill road?",
        ],
    },
    "consequence_signals_emit_bounded_social_signal": {
        "currency": {"gold": 0, "silver": 0, "copper": 0},
        "conversation_settings": {
            "enabled": True,
            "autonomous_ticks_enabled": True,
            "frequency": "always",
            "conversation_chance_percent": 100,
            "allow_player_invited": True,
            "player_inclusion_chance_percent": 100,
            "player_reputation_consequences_enabled": True,
            "consequence_signals_enabled": True,
            "min_ticks_between_conversations": 0,
            "thread_cooldown_ticks": 0,
        },
        "turns": [
            "__ambient_tick_player_invited__",
            "Thank you, that was helpful.",
        ],
    },
}