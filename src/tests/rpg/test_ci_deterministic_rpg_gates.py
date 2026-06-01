from app.rpg.progression.graph_registry import validate_progression_graph_registry
from app.rpg.progression.runtime import (
    apply_progression_for_action,
    get_active_progression_actions,
)
from tests.rpg.autoplay.campaign_report import render_campaign_report_html


def test_ci_progression_registry_is_valid():
    result = validate_progression_graph_registry()

    assert result["ok"] is True
    assert result["graph_count"] >= 1
    assert result["node_count"] >= 1


def test_ci_progression_actions_are_seed_specific_and_concrete():
    tavern_actions = get_active_progression_actions(
        {},
        scenario_seed="tavern_story_seed",
        limit=3,
    )
    caravan_actions = get_active_progression_actions(
        {},
        scenario_seed="caravan_ambush_seed",
        limit=3,
    )

    assert tavern_actions
    assert caravan_actions
    assert tavern_actions[0]["source"] == "scenario_progression_graph"
    assert caravan_actions[0]["source"] == "scenario_progression_graph"
    assert tavern_actions[0]["graph_id"] != caravan_actions[0]["graph_id"]
    assert "follow up on the lead" not in tavern_actions[0]["command"].lower()


def test_ci_progression_applies_first_tavern_node_and_unlocks_next_lead():
    result = apply_progression_for_action(
        {},
        scenario_seed="tavern_story_seed",
        player_action="I ask Bran why the tavern feels so tense tonight.",
        turn_index=1,
    )

    assert result["ok"] is True
    assert result["changed"] is True
    state = result["state"]
    assert "ask_bran_about_tension" in state["progression_completed_nodes"]
    assert "fact:witness_left_side_door" in state["progression_facts"]
    assert "npc:mira" in state["progression_unlocked_npcs"]

    next_action_ids = [
        row["action_id"]
        for row in get_active_progression_actions(
            state,
            scenario_seed="tavern_story_seed",
            limit=8,
        )
    ]
    assert "ask_bran_who_left_side_door" in next_action_ids


def test_ci_campaign_report_renders_progression_summary_section():
    html = render_campaign_report_html(
        {
            "scenario_seed": "ci_smoke",
            "scenario_progression_arc_summary": {
                "graph_id": "graph:tavern_story_seed",
                "arc_complete": False,
                "expected_node_count": 2,
                "completed_node_count": 1,
                "completed_node_ids": ["ask_bran_about_tension"],
                "remaining_node_ids": ["ask_bran_who_left_side_door"],
            },
            "progression_completed_nodes": {
                "ask_bran_about_tension": {},
            },
            "scenario_progression_log": [
                {"turn_index": 1, "matched_node_ids": ["ask_bran_about_tension"]},
            ],
        }
    )

    assert "html" in html.lower()
    assert "Scenario Progression Graph" in html
    assert "ask bran about tension" in html
