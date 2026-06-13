from __future__ import annotations

from app.rpg.ai.world_scene_narrator_prompts import build_scene_prompt


def test_scene_prompt_promotes_current_turn_semantic_visible_response_over_old_thread() -> None:
    visible_response = {
        "narration": "You sigh and admit the last few days have worn you down.",
        "npc": {
            "speaker": "Bran the Innkeeper",
            "line": "Rough, eh? Come on now, friend. Tell old Bran about it.",
        },
    }
    prompt = build_scene_prompt(
        {
            "title": "The Rusty Flagon Tavern",
            "summary": "A warm tavern room with Bran behind the counter.",
            "actors": [{"id": "bran", "name": "Bran the Innkeeper"}],
            "location_name": "The Rusty Flagon Tavern",
        },
        {
            "player_input": "ive had a rough few day ma man",
            "resolved_result": {
                "message": "You express that you have had a rough few days.",
            },
            "turn_contract": {
                "player_input": "ive had a rough few day ma man",
                "action": {
                    "action_type": "social_activity",
                    "target_id": "bran",
                    "target_name": "Bran the Innkeeper",
                    "metadata": {
                        "semantic_action": {
                            "visible_response": visible_response,
                        },
                    },
                },
                "semantic_action": {
                    "action_type": "social_activity",
                    "target_id": "bran",
                    "target_name": "Bran the Innkeeper",
                    "visible_response": visible_response,
                },
                "resolved_result": {
                    "message": "You express that you have had a rough few days.",
                },
                "narration_brief": {
                    "summary": "You tell Bran that you have had a rough few days.",
                },
            },
            "conversation_threads": [
                {
                    "thread_id": "thread:bran-day",
                    "participants": ["player", "Bran the Innkeeper"],
                    "topic": {"summary": "Bran asked how your day was going."},
                    "recent_lines": [
                        {
                            "speaker_name": "Bran the Innkeeper",
                            "text": "How about yourself? What kind of day have you had?",
                        }
                    ],
                }
            ],
            "simulation_state": {},
            "runtime_state": {},
        },
    )

    assert "CURRENT_TURN_SEMANTIC_VISIBLE_RESPONSE_JSON" in prompt
    assert "Tell old Bran about it" in prompt
    assert "outranks conversation_threads recent_lines" in prompt
    assert "Do not copy an older NPC question" in prompt

