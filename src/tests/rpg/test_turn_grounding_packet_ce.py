from __future__ import annotations

import json

from app.rpg.ai.action_intelligence import build_action_intelligence_prompt, normalize_action_advisory
from app.rpg.ai.semantic_action_intelligence import build_semantic_action_prompt, normalize_semantic_action_advisory
from app.rpg.session.turn_grounding import build_turn_grounding_packet


def _sample_states():
    simulation_state = {
        "player_state": {
            "location_id": "loc:tavern",
            "nearby_npc_ids": ["npc:bran"],
            "stats": {"strength": 2},
            "skills": {"swordsmanship": {"level": 1}},
            "inventory_state": {
                "currency": {"silver": 3},
                "items": [{"id": "item:practice_sword", "name": "Practice sword"}],
            },
        },
        "npc_index": {
            "npc:bran": {
                "id": "npc:bran",
                "name": "Bran",
                "role": "innkeeper and former caravan guard",
                "location_id": "loc:tavern",
                "biography": {
                    "public": "Bran owns the Ashroad Tavern. Before settling down, he guarded caravans through bandit country and learned practical sword-and-shield habits.",
                    "private": "Bran blames himself for leaving a friend behind during an ambush.",
                },
                "personality": {
                    "summary": "Bran is practical, guarded, and slow to trust, but respects courage and plain speech.",
                    "values": ["survival", "earned loyalty", "plain speech"],
                    "fears": ["another ambush", "losing the tavern"],
                    "speech_style": "Plain, direct, road-worn advice with little patience for fancy boasts.",
                    "speech_examples": [
                        "A pretty stance means nothing if your feet slip in the mud.",
                        "Keep your guard where the next blow is coming from.",
                    ],
                },
                "capabilities": {
                    "combat_style": "defensive sword-and-shield",
                    "skills": ["caravan routes", "basic swordplay", "local rumors"],
                },
                "inventory": {
                    "visible": ["worn short sword", "tavern key ring"],
                    "private": ["sealed letter from an old caravan contact"],
                },
                "knowledge_boundaries": {
                    "may_discuss": ["road survival", "basic sword habits"],
                    "must_not_reveal": ["private caravan guilt unless earned in play"],
                },
            }
        },
        "relationships": {"npc:bran": {"trust": 42, "respect": 35}},
    }
    runtime_state = {
        "current_scene": {
            "scene_id": "scene:tavern_common_room",
            "location_id": "loc:tavern",
            "location_name": "Ashroad Tavern",
            "summary": "A low, smoky tavern room near the old road.",
            "present_npc_ids": ["npc:bran"],
        },
        "turn_history": [{"player_input": "Any work nearby?", "summary": "Bran warned about the old road."}],
        "combat_state": {"active": False},
    }
    return simulation_state, runtime_state


def test_grounding_packet_includes_rich_bran_profile_and_boundaries():
    simulation_state, runtime_state = _sample_states()
    packet = build_turn_grounding_packet(
        player_input="Bran, what do you think about sword combat styles?",
        simulation_state=simulation_state,
        runtime_state=runtime_state,
        candidate_action={"action_type": "observe"},
    )

    assert packet["format_version"] == "turn_grounding_packet_v1"
    assert packet["priority_context"]["addressed_npc_ids"] == ["npc:bran"]
    bran = packet["npc_context"]["addressed_npcs"][0]
    assert "guarded caravans" in bran["biography"]["public"]
    assert "practical" in bran["personality_profile"]["summary"].lower()
    assert bran["personality_profile"]["speech_examples"]
    assert "sealed letter" in bran["inventory"]["private"][0]
    assert packet["rules"]["first_llm_may_answer_non_stateful_interpretive_dialogue"] is True
    assert packet["rules"]["first_llm_must_not_resolve_stateful_outcomes"] is True


def test_action_prompt_embeds_grounding_packet_for_first_llm_call():
    simulation_state, runtime_state = _sample_states()
    prompt = build_action_intelligence_prompt(
        "Bran, what do you think about sword combat styles?",
        simulation_state,
        runtime_state,
        {"action_type": "observe"},
    )
    assert "turn_grounding_packet" in prompt
    assert "Bran owns the Ashroad Tavern" in prompt
    assert "first-call action-intent extraction" in prompt
    assert "Do not decide outcomes" in prompt

    payload = json.loads(prompt.split("INPUT:\n", 1)[1])
    assert payload["turn_grounding_packet"]["npc_context"]["addressed_npcs"][0]["name"] == "Bran"


def test_semantic_prompt_supports_non_stateful_visible_response_contract():
    simulation_state, runtime_state = _sample_states()
    prompt = build_semantic_action_prompt(
        "Bran, what do you think about sword combat styles?",
        simulation_state,
        runtime_state,
        {"action_type": "observe"},
    )
    assert "stateful false" in prompt
    assert "visible_response" in prompt
    assert "Never reveal private_context" in prompt

    normalized = normalize_semantic_action_advisory(
        {
            "action_type": "social_activity",
            "semantic_family": "social",
            "interaction_mode": "direct",
            "activity_label": "opinion_on_sword_styles",
            "target_id": "npc:bran",
            "stateful": False,
            "needs_runtime_resolution": False,
            "visible_response": {
                "narration": "Bran considers the question.",
                "npc": {"speaker": "Bran", "line": "Fancy styles fail when boots hit mud."},
            },
        },
        {"action_type": "observe"},
    )
    assert normalized["stateful"] is False
    assert normalized["needs_runtime_resolution"] is False
    assert normalized["visible_response"]["npc"]["speaker"] == "Bran"


def test_stateful_purchase_intent_remains_runtime_resolved():
    normalized = normalize_action_advisory(
        {
            "action_type": "trade",
            "target_id": "npc:bran",
            "target_name": "bread",
            "stateful": True,
            "needs_runtime_resolution": True,
            "visible_response": {
                "npc": {"speaker": "Bran", "line": "That will be one copper."}
            },
        },
        {"action_type": "observe"},
    )
    assert normalized["action_type"] == "trade"
    assert normalized["stateful"] is True
    assert normalized["needs_runtime_resolution"] is True
    assert normalized["grounding_packet_version"] == "turn_grounding_packet_v1"
