from app.rpg.progression.graph_registry import validate_progression_graph_registry
from app.rpg.progression.runtime import (
    apply_progression_for_action,
    get_active_progression_actions,
)
from tests.rpg.autoplay.campaign_report import render_campaign_report_html


def test_ci_progression_registry_is_valid():
    result = validate_progression_graph_registry()

    assert isinstance(result, dict)
    assert result.get("ok") is True


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
    assert tavern_actions[0].get("source") == "scenario_progression_graph"
    assert caravan_actions[0].get("source") == "scenario_progression_graph"
    assert tavern_actions[0].get("command")
    assert caravan_actions[0].get("command")
    assert "follow up on the lead" not in tavern_actions[0]["command"].lower()


def test_ci_progression_applies_first_tavern_node_and_unlocks_next_actions():
    result = apply_progression_for_action(
        {},
        scenario_seed="tavern_story_seed",
        player_action="I ask Bran for a room, but I also ask why the tavern feels so tense tonight.",
        turn_index=1,
    )

    assert result.get("ok") is True
    assert result.get("changed") is True
    state = result["state"]
    assert "ask_bran_about_tension" in state.get("progression_completed_nodes", {})
    assert "fact:witness_left_side_door" in state.get("progression_facts", {})

    next_actions = get_active_progression_actions(
        state,
        scenario_seed="tavern_story_seed",
        limit=8,
    )
    assert next_actions
    assert any(row.get("source") == "scenario_progression_graph" for row in next_actions)


def test_ci_campaign_report_renders_html():
    html = render_campaign_report_html({"scenario_seed": "ci_smoke"})

    assert isinstance(html, str)
    assert "html" in html.lower()
    assert "report" in html.lower() or "campaign" in html.lower() or "ci_smoke" in html
