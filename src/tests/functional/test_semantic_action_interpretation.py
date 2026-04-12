"""Functional tests for semantic action intelligence interpretation."""

from typing import Any, Dict

import pytest

from app.rpg.ai.semantic_action_intelligence import get_semantic_action_advisory
from app.rpg.llm_app_gateway import build_app_llm_gateway


@pytest.mark.functional
def test_semantic_action_interpretation_darts_challenge():
    """Test that 'challenge Bran to darts' is interpreted as social_competition."""
    _test_semantic_interpretation(
        player_input="I challenge Bran to darts",
        expected_action_type="social_competition",
        expected_activity_label="darts",
        expected_target_id="npc_bran",
    )


@pytest.mark.functional
def test_semantic_action_interpretation_hug():
    """Test that 'hug Elara' is interpreted as social_affection."""
    _test_semantic_interpretation(
        player_input="I hug Elara",
        expected_action_type="social_affection",
        expected_activity_label="hug",
        expected_target_id="npc_elara",
    )


@pytest.mark.functional
def test_semantic_action_interpretation_buy_drinks():
    """Test that 'buy everyone a round' is interpreted as social_activity."""
    _test_semantic_interpretation(
        player_input="I buy everyone a round of drinks",
        expected_action_type="social_activity",
        expected_activity_label="buying_drinks",
    )


@pytest.mark.functional
def test_semantic_action_interpretation_sing_song():
    """Test that 'sing a song' is interpreted as social_performance."""
    _test_semantic_interpretation(
        player_input="I sing a song for the tavern",
        expected_action_type="social_performance",
        expected_activity_label="song",
    )


@pytest.mark.functional
def test_semantic_action_interpretation_investigate():
    """Test that 'look around' is interpreted as exploration."""
    _test_semantic_interpretation(
        player_input="I look around the tavern carefully",
        expected_action_type="exploration",
        expected_semantic_family="exploration",
    )


@pytest.mark.functional
def test_semantic_action_interpretation_ritual():
    """Test that 'perform a ritual' is interpreted as ritual."""
    _test_semantic_interpretation(
        player_input="I perform an ancient ritual",
        expected_action_type="ritual",
        expected_semantic_family="ritual",
    )


@pytest.mark.functional
def test_semantic_action_interpretation_threat():
    """Test that 'threaten the guard' is interpreted as threat."""
    _test_semantic_interpretation(
        player_input="I threaten Captain Aldric with my sword",
        expected_action_type="threat",
        expected_semantic_family="threat",
        expected_target_id="npc_aldric",
    )


def _test_semantic_interpretation(
    player_input: str,
    expected_action_type: str = None,
    expected_activity_label: str = None,
    expected_semantic_family: str = None,
    expected_target_id: str = None,
):
    """Helper to test semantic action interpretation."""

    # Mock simulation state similar to the tavern scene
    simulation_state = {
        "tick": 100,
        "player_state": {
            "location_id": "loc:tavern",
            "nearby_npc_ids": ["npc_bran", "npc_elara", "npc_aldric"],
            "stats": {"charisma": 12, "intelligence": 10},
            "skills": {"persuasion": {"level": 2}},
        },
        "npc_index": {
            "npc_bran": {
                "id": "npc_bran",
                "name": "Bran the Innkeeper",
                "role": "innkeeper",
                "location_id": "loc:tavern",
            },
            "npc_elara": {
                "id": "npc_elara",
                "name": "Elara the Merchant",
                "role": "merchant",
                "location_id": "loc:tavern",
            },
            "npc_aldric": {
                "id": "npc_aldric",
                "name": "Captain Aldric",
                "role": "guard",
                "location_id": "loc:tavern",
            },
        },
    }

    runtime_state = {
        "tick": 100,
        "current_scene": {
            "scene_id": "scene:tavern",
            "location_id": "loc:tavern",
            "summary": "A lively tavern scene with patrons drinking and talking.",
        },
    }

    candidate_action = {
        "action_type": "social_activity",
        "target_id": "",
        "target_name": "",
    }

    llm_gateway = build_app_llm_gateway()

    # Get semantic advisory
    semantic_advisory = get_semantic_action_advisory(
        llm_gateway=llm_gateway,
        player_input=player_input,
        simulation_state=simulation_state,
        runtime_state=runtime_state,
        candidate_action=candidate_action,
    )

    assert semantic_advisory, f"No semantic advisory generated for input: {player_input}"

    if expected_action_type:
        assert semantic_advisory.get("action_type") == expected_action_type, \
            f"Expected action_type {expected_action_type}, got {semantic_advisory.get('action_type')}"

    if expected_activity_label:
        assert semantic_advisory.get("activity_label") == expected_activity_label, \
            f"Expected activity_label {expected_activity_label}, got {semantic_advisory.get('activity_label')}"

    if expected_semantic_family:
        assert semantic_advisory.get("semantic_family") == expected_semantic_family, \
            f"Expected semantic_family {expected_semantic_family}, got {semantic_advisory.get('semantic_family')}"

    if expected_target_id:
        assert semantic_advisory.get("target_id") == expected_target_id, \
            f"Expected target_id {expected_target_id}, got {semantic_advisory.get('target_id')}"

    # Basic structure validation
    required_fields = [
        "action_type", "semantic_family", "interaction_mode",
        "activity_label", "target_id", "target_name", "visibility",
        "intensity", "stakes", "social_axes", "observer_hooks",
        "scene_impact", "reason"
    ]
    for field in required_fields:
        assert field in semantic_advisory, f"Missing required field: {field}"

    print(f"\n✓ '{player_input}' → {semantic_advisory.get('action_type')} ({semantic_advisory.get('activity_label')})")


if __name__ == "__main__":
    # Allow running individual tests from command line
    import sys
    if len(sys.argv) > 1:
        test_name = sys.argv[1]
        if test_name in globals():
            globals()[test_name]()
            print(f"✓ {test_name} passed")
        else:
            print(f"Test {test_name} not found")
    else:
        # Run all tests
        pytest.main([__file__, "-v"])