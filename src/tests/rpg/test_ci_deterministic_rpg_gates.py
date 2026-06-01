def test_ci_progression_registry_exposes_tavern_graphs():
    from app.rpg.progression.graph_registry import get_progression_graphs_for_seed

    graphs = get_progression_graphs_for_seed("tavern_story_seed")

    assert graphs
    assert graphs[0].graph_id
    assert graphs[0].nodes


def test_ci_progression_actions_are_available_for_tavern_seed():
    from app.rpg.progression.runtime import get_active_progression_actions

    actions = get_active_progression_actions(
        {},
        scenario_seed="tavern_story_seed",
        limit=3,
    )

    assert actions
    assert actions[0].get("command")
    assert "follow up on the lead" not in actions[0]["command"].lower()


def test_ci_campaign_report_renderer_is_importable():
    from tests.rpg.autoplay.campaign_report import render_campaign_report_html

    html = render_campaign_report_html({"scenario_seed": "ci_smoke"})

    assert isinstance(html, str)
    assert html.strip()
