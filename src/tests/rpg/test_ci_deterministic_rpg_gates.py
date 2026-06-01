from app.rpg.progression.graph_registry import validate_progression_graph_registry
from app.rpg.progression.runtime import get_active_progression_actions
from tests.rpg.autoplay.campaign_report import render_campaign_report_html


def test_ci_progression_registry_is_importable_and_validates():
    result = validate_progression_graph_registry()

    assert isinstance(result, dict)
    assert result.get("ok") is True


def test_ci_progression_actions_are_available_for_tavern_seed():
    actions = get_active_progression_actions(
        {},
        scenario_seed="tavern_story_seed",
        limit=3,
    )

    assert actions
    assert actions[0].get("command")
    assert "follow up on the lead" not in actions[0]["command"].lower()


def test_ci_campaign_report_renderer_is_importable():
    html = render_campaign_report_html({"scenario_seed": "ci_smoke"})

    assert isinstance(html, str)
    assert html.strip()
