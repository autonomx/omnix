from tests.rpg.autoplay_llm_campaign import (
    _action_violates_anti_loop,
    _build_player_agent_anti_loop_context,
    _deterministic_anti_loop_fallback_action,
    _rough_semantic_pair_for_player_action,
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