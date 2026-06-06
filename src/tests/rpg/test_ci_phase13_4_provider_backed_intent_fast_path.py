from app.rpg.session.provider_backed_intent_fast_path import (
    FAST_PATH_SOURCE,
    build_provider_backed_fast_path_advisory,
    provider_backed_fast_path_enabled,
)
from tests.rpg.interactive_intent_matrix_latency_reduction import provider_backed_matrix_fast_path_patch


def _override():
    return {"fast_turn_mode": True, "enable_provider_backed_intent_fast_path": True}


def test_phase13_4_fast_path_is_opt_in():
    assert provider_backed_fast_path_enabled({}) is False
    assert provider_backed_fast_path_enabled({"fast_turn_mode": False}) is False
    assert provider_backed_fast_path_enabled({"fast_turn_mode": True}) is True
    assert provider_backed_fast_path_enabled({"fast_turn_mode": True, "enable_provider_backed_intent_fast_path": False}) is False


def test_phase13_4_bounded_provider_backed_categories_get_fast_advisories():
    cases = {
        "Any rumors around here?": ("rumor_inquiry", "rumor_news_no_backed_state"),
        "Any news lately, Bran?": ("rumor_inquiry", "rumor_news_no_backed_state"),
        "I'm looking for a quest.": ("quest_inquiry", "quest_no_backed_state"),
        "What food do you have for sale?": ("service_inquiry", "commerce_food_purchase"),
        "I'll buy a hot stew.": ("service_purchase", "commerce_food_purchase"),
        "Bran, will you join my party as a companion?": ("talk", "party_companion_recruitment"),
        "Bran, who are you?": ("talk", "npc_dialogue_persona"),
    }
    for player_input, (action_type, category) in cases.items():
        advisory = build_provider_backed_fast_path_advisory(
            player_input=player_input,
            performance_override=_override(),
        )
        assert advisory["source"] == FAST_PATH_SOURCE
        assert advisory["action_type"] == action_type
        assert advisory["target_id"] == "npc:Bran"
        assert advisory["stateful"] is True
        assert advisory["needs_runtime_resolution"] is True
        assert advisory["fast_path_category"] == category
        diagnostics = advisory["first_call_grounding_diagnostics"]
        assert diagnostics["source"] == FAST_PATH_SOURCE
        assert diagnostics["provider_parse_ok"] is True
        assert diagnostics["turn_grounding_packet"]["fast_path_category"] == category


def test_phase13_4_fast_path_does_not_match_unbounded_inputs():
    assert build_provider_backed_fast_path_advisory(
        player_input="I invent a spell and reshape the tavern.",
        performance_override=_override(),
    ) == {}
    assert build_provider_backed_fast_path_advisory(
        player_input="Any rumors around here?",
        performance_override={"fast_turn_mode": False},
    ) == {}


def test_phase13_4_patch_restores_runtime_functions():
    from app.rpg.session import interactive_first_call_runtime as runtime

    original_action = runtime.get_action_advisory
    original_semantic = runtime.get_semantic_action_advisory
    with provider_backed_matrix_fast_path_patch():
        assert runtime.get_action_advisory is not original_action
        advisory = runtime.get_action_advisory(
            llm_gateway=object(),
            player_input="Any rumors around here?",
            simulation_state={},
            runtime_state={},
            candidate_action={},
            performance_override=_override(),
        )
        assert advisory["source"] == FAST_PATH_SOURCE
        assert runtime.get_semantic_action_advisory(
            llm_gateway=object(),
            player_input="Any rumors around here?",
            simulation_state={},
            runtime_state={},
            candidate_action={},
            performance_override=_override(),
        ) == {}
    assert runtime.get_action_advisory is original_action
    assert runtime.get_semantic_action_advisory is original_semantic
