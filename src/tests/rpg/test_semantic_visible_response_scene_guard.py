from __future__ import annotations

from app.rpg.session import runtime_part38


def test_semantic_visible_response_rejects_scene_speaker_player_restatement():
    source = {
        "action_type": "social_activity",
        "semantic_family": "social",
        "interaction_mode": "direct",
        "target_id": "scene",
        "target_name": "Scene",
        "stateful": False,
        "needs_runtime_resolution": False,
        "visible_response": {
            "narration": "I ask Bran if he has any food for sale",
            "npc": {
                "speaker": "Scene",
                "line": "I ask Bran if he has any food for sale",
            },
        },
        "direct_response_gate": {
            "safe_to_display_now": True,
            "reason": "non_mutating_dialogue",
            "risk_flags": ["social"],
        },
        "first_call_grounding_diagnostics": {
            "turn_grounding_packet": {
                "player_input": "I ask Bran if he has any food for sale",
            },
        },
    }

    assert runtime_part38._phase8_part38_candidate_from_source(source) == {}


def test_semantic_visible_response_rejects_scene_speaker_even_with_new_line():
    source = {
        "action_type": "social_activity",
        "semantic_family": "social",
        "interaction_mode": "direct",
        "target_id": "scene",
        "target_name": "Scene",
        "stateful": False,
        "needs_runtime_resolution": False,
        "visible_response": {
            "narration": "The tavern noise settles around your question.",
            "npc": {
                "speaker": "Scene",
                "line": "Food and drink are available at the bar.",
            },
        },
        "direct_response_gate": {
            "safe_to_display_now": True,
            "reason": "non_mutating_dialogue",
            "risk_flags": ["social"],
        },
        "first_call_grounding_diagnostics": {
            "turn_grounding_packet": {
                "player_input": "I ask Bran if he has food for sale",
            },
        },
    }

    assert runtime_part38._phase8_part38_candidate_from_source(source) == {}
