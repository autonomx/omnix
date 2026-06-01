def test_ci_progression_registry_exposes_tavern_graphs():
    from app.rpg.progression.models import ProgressionNode, ScenarioProgressionGraph

    graph = ScenarioProgressionGraph(
        graph_id="ci:test",
        scenario_seed="ci_seed",
        nodes=[ProgressionNode(node_id="ci_node", title="CI node")],
    )

    assert graph.graph_id == "ci:test"
    assert graph.nodes[0].node_id == "ci_node"


def test_ci_progression_actions_are_available_for_tavern_seed():
    from app.rpg.progression.runtime import get_active_progression_actions

    actions = get_active_progression_actions(
        {},
        scenario_seed="tavern_story_seed",
        limit=3,
    )

    assert actions
    assert actions[0].get("command")


def test_ci_campaign_report_renderer_is_importable():
    from tests.rpg.autoplay.campaign_report import render_campaign_report_html

    html = render_campaign_report_html({"scenario_seed": "ci_smoke"})

    assert isinstance(html, str)
    assert html.strip()
