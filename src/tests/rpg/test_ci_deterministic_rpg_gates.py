def test_ci_progression_registry_is_importable_and_returns_inventory():
    from app.rpg.progression.graph_registry import validate_progression_graph_registry

    result = validate_progression_graph_registry()

    assert isinstance(result, dict)
    assert isinstance(result.get("errors"), list)
    assert result.get("graph_count", 0) >= 1
    assert "tavern_story_seed" in result.get("seeds", [])


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
