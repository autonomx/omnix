from tests.rpg.autoplay_llm_campaign import (
    _action_violates_anti_loop,
    _build_player_agent_anti_loop_context,
    _deterministic_anti_loop_fallback_action,
    _rough_semantic_pair_for_player_action,
)
from tests.rpg.autoplay.hundred_turn_eval import (
    canonical_semantic_pair_from_turn,
    recent_semantic_target_streak,
)


def test_build_player_agent_anti_loop_context_activates_on_repeated_pair():
    transcript = [
        {"semantic_action": "observe", "semantic_target": "Bran"},
        {"semantic_action": "observe", "semantic_target": "Bran"},
        {"semantic_action": "observe", "semantic_target": "Bran"},
    ]

    context = _build_player_agent_anti_loop_context(
        transcript=transcript,
        threshold=3,
        window=8,
    )

    assert context["active"] is True
    assert context["pair"] == "observe:Bran"
    assert context["streak"] == 3
    assert context["target"] == "Bran"


def test_action_violates_anti_loop_for_observe_same_target():
    context = {
        "active": True,
        "pair": "observe:Bran",
        "semantic_action": "observe",
        "target": "Bran",
        "streak": 4,
    }

    assert _action_violates_anti_loop(
        "Wait patiently and maintain eye contact with Bran.",
        context,
    )
    assert not _action_violates_anti_loop(
        "Turn away from Bran and ask a nearby patron about Silas.",
        context,
    )


def test_rough_semantic_pair_classifies_service_and_travel_actions():
    assert _rough_semantic_pair_for_player_action("Pay Bran for a room.")["semantic_action"] == "service"
    assert _rough_semantic_pair_for_player_action("Step outside and head to the road.")["semantic_action"] == "travel"


def test_deterministic_anti_loop_fallback_changes_target_for_bran():
    action = _deterministic_anti_loop_fallback_action(
        {"target": "Bran", "semantic_action": "observe", "pair": "observe:Bran"}
    )
    assert "nearby patron" in action.lower()
    assert "turn away from bran" in action.lower()


def test_anti_loop_context_includes_concrete_alternatives():
    context = _build_player_agent_anti_loop_context(
        transcript=[
            {"semantic_action": "observe", "semantic_target": "Bran"},
            {"semantic_action": "observe", "semantic_target": "Bran"},
            {"semantic_action": "observe", "semantic_target": "Bran"},
        ],
        threshold=3,
        window=8,
    )

    assert context["active"] is True
    assert any("different target" in item.lower() for item in context["alternatives"])
    assert any("service" in item.lower() for item in context["alternatives"])


def test_canonical_semantic_pair_reads_semantic_action_v2_shape():
    row = {
        "semantic_action_v2": {
            "semantic_action": "observe",
            "target": "Bran",
        }
    }

    result = canonical_semantic_pair_from_turn(row)

    assert result["semantic_action"] == "observe"
    assert result["target"] == "Bran"
    assert result["pair"] == "observe:Bran"


def test_canonical_semantic_pair_reads_turn_contract_shape():
    row = {
        "turn_contract": {
            "semantic_action": "service_inquiry",
            "target": "Bran",
        }
    }

    result = canonical_semantic_pair_from_turn(row)

    assert result["semantic_action"] == "service_inquiry"
    assert result["target"] == "Bran"
    assert result["pair"] == "service_inquiry:Bran"


def test_recent_semantic_target_streak_uses_canonical_extraction_not_unknown_unknown():
    transcript = [
        {
            "semantic_action_v2": {
                "semantic_action": "observe",
                "target": "Bran",
            }
        },
        {
            "semantic_action_v2": {
                "semantic_action": "observe",
                "target": "Bran",
            }
        },
        {
            "semantic_action_v2": {
                "semantic_action": "observe",
                "target": "Bran",
            }
        },
    ]

    streak = recent_semantic_target_streak(transcript, window=8)

    assert streak["pair"] == "observe:Bran"
    assert streak["semantic_action"] == "observe"
    assert streak["target"] == "Bran"
    assert streak["streak"] == 3
    assert streak["source"] == "canonical_semantic_pair_from_turn"


def test_player_agent_anti_loop_context_reports_canonical_recent_pairs():
    transcript = [
        {
            "semantic_action_v2": {
                "semantic_action": "observe",
                "target": "Bran",
            }
        },
        {
            "semantic_action_v2": {
                "semantic_action": "observe",
                "target": "Bran",
            }
        },
        {
            "semantic_action_v2": {
                "semantic_action": "observe",
                "target": "Bran",
            }
        },
    ]

    context = _build_player_agent_anti_loop_context(
        transcript=transcript,
        threshold=3,
        window=8,
    )

    assert context["active"] is True
    assert context["pair"] == "observe:Bran"
    assert context["source"] == "canonical_semantic_pair_from_turn"
    assert context["recent_pairs"][-1] == "observe:Bran"
    assert context["canonical_recent_pairs"][-1]["pair"] == "observe:Bran"


def test_canonical_semantic_pair_reads_nested_turn_contract_action_metadata_semantic_action():
    row = {
        "turn_contract": {
            "action": {
                "action_type": "service_inquiry",
                "target": "npc:Bran",
                "metadata": {
                    "semantic_action": {
                        "action_type": "service_inquiry",
                        "target_name": "Bran",
                        "target_id": "npc:Bran",
                    }
                },
            }
        }
    }

    result = canonical_semantic_pair_from_turn(row)

    assert result["semantic_action"] == "service_inquiry"
    assert result["target"] == "Bran"
    assert result["pair"] == "service_inquiry:Bran"
    assert result["source"] == "row.turn_contract.action.metadata.semantic_action"


def test_canonical_semantic_pair_reads_turn_contract_action_when_metadata_missing():
    row = {
        "turn_contract": {
            "action": {
                "action_type": "rent_room",
                "target": "inn",
            }
        }
    }

    result = canonical_semantic_pair_from_turn(row)

    assert result["semantic_action"] == "rent_room"
    assert result["target"] == "inn"
    assert result["pair"] == "rent_room:inn"
    assert result["source"] == "row.turn_contract.action"


def test_canonical_semantic_pair_reads_resolved_action_semantic_action():
    row = {
        "turn_contract": {
            "resolved_action": {
                "semantic_action": {
                    "action_type": "observe",
                    "target_name": "Cloaked Traveler",
                }
            }
        }
    }

    result = canonical_semantic_pair_from_turn(row)

    assert result["semantic_action"] == "observe"
    assert result["target"] == "Cloaked Traveler"
    assert result["pair"] == "observe:Cloaked Traveler"
    assert result["source"] == "row.turn_contract.resolved_action.semantic_action"


def test_anti_loop_context_uses_nested_turn_contract_semantic_pairs_not_unknown_unknown():
    transcript = [
        {
            "turn_contract": {
                "action": {
                    "metadata": {
                        "semantic_action": {
                            "action_type": "service_inquiry",
                            "target_name": "Bran",
                            "target_id": "npc:Bran",
                        }
                    }
                }
            }
        },
        {
            "turn_contract": {
                "action": {
                    "metadata": {
                        "semantic_action": {
                            "action_type": "service_inquiry",
                            "target_name": "Bran",
                            "target_id": "npc:Bran",
                        }
                    }
                }
            }
        },
        {
            "turn_contract": {
                "action": {
                    "metadata": {
                        "semantic_action": {
                            "action_type": "service_inquiry",
                            "target_name": "Bran",
                            "target_id": "npc:Bran",
                        }
                    }
                }
            }
        },
    ]

    context = _build_player_agent_anti_loop_context(
        transcript=transcript,
        threshold=3,
        window=8,
    )

    assert context["active"] is True
    assert context["pair"] == "service_inquiry:Bran"
    assert context["streak"] == 3
    assert context["source"] == "canonical_semantic_pair_from_turn"
    assert context["recent_pairs"][-1] == "service_inquiry:Bran"
    assert context["canonical_recent_pairs"][-1]["source"] == (
        "row.turn_contract.action.metadata.semantic_action"
    )


def test_canonical_semantic_pair_text_fallback_for_player_input():
    row = {
        "player_input": "I ask Bran about lodging and whether I can rent a room for the night."
    }

    result = canonical_semantic_pair_from_turn(row)

    assert result["semantic_action"] == "rent_room"
    assert result["target"] in ("Bran", "inn")
    assert result["pair"] != "unknown:unknown"
    assert result["source"] == "player_action_text_fallback"