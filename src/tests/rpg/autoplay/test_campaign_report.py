
from tests.rpg.autoplay import campaign_report
from tests.rpg.autoplay.campaign_report import (
    render_campaign_report_html,
)


def test_campaign_report_prefers_latest_state_quest_progress_summary():
    model = {
        "quest_progress_summary": {
            "quest_count": 1,
            "completed_count": 0,
            "active_count": 1,
            "quests": [
                {
                    "quest_id": "quest:witness_search",
                    "title": "Witness Search",
                    "status": "active",
                    "objective_count": 2,
                    "completed_objective_count": 0,
                }
            ],
        },
        "latest_state": {
            "quest_progress": {
                "quests": {
                    "quest:witness_search": {
                        "quest_id": "quest:witness_search",
                        "title": "Witness Search",
                        "status": "completed",
                        "completed": True,
                        "objectives": [
                            {"summary": "Find the witness.", "status": "completed", "completed": True},
                            {"summary": "Report findings to Bran.", "status": "completed", "completed": True},
                        ],
                    },
                    "quest:bandit_road": {
                        "quest_id": "quest:bandit_road",
                        "title": "Bandit Road",
                        "status": "active",
                        "objectives": [
                            {"summary": "Prepare for the bandit road.", "status": "active", "completed": False}
                        ],
                    },
                }
            }
        },
    }

    summary = campaign_report._quest_summary_from_latest_state(model)
    assert summary["completed_count"] == 1
    assert summary["active_count"] == 1
    witness = [row for row in summary["quests"] if row["quest_id"] == "quest:witness_search"][0]
    assert witness["status"] == "completed"
    assert witness["completed_objective_count"] == 2


def test_report_includes_progression_graph_section():

    summary = {
        "scenario_progression_arc_summary": {
            "graph_id": "graph:tavern_story_seed",
            "arc_complete": True,
            "expected_node_count": 2,
            "completed_node_count": 2,
            "completed_node_ids": ["ask_bran_about_tension", "ask_bran_who_left_side_door"],
            "remaining_node_ids": [],
        },
        "progression_completed_nodes": {
            "ask_bran_about_tension": {},
            "ask_bran_who_left_side_door": {},
        },
        "scenario_progression_log": [
            {"turn_index": 1, "matched_node_ids": ["ask_bran_about_tension"]},
            {"turn_index": 2, "matched_node_ids": ["ask_bran_who_left_side_door"]},
        ],
    }

    html = render_campaign_report_html(summary)

    assert "Scenario Progression Graph" in html
    assert "Nodes are ordered by first matched turn" in html
    assert "ask bran about tension" in html
    assert "ask bran who left side door" in html
    assert "Mermaid graph source" in html


def test_progression_graph_report_orders_nodes_by_turn_not_alphabetically():
    from tests.rpg.autoplay.campaign_report import _progression_graph_report_data

    summary = {
        "scenario_seed": "tavern_story_seed",
        "scenario_progression_arc_summary": {
            "graph_id": "graph:tavern_story_seed",
            "arc_complete": True,
            "expected_node_count": 4,
            "completed_node_count": 4,
            # This intentionally mimics run 199's problem: completed_node_ids may
            # be sorted or non-chronological.
            "completed_node_ids": [
                "ask_alternate_route",
                "ask_bran_about_tension",
                "ask_bran_bridge",
                "report_findings_to_bran",
            ],
            "remaining_node_ids": [],
        },
        "progression_completed_nodes": {
            "ask_alternate_route": {},
            "ask_bran_about_tension": {},
            "ask_bran_bridge": {},
            "report_findings_to_bran": {},
        },
        "scenario_progression_log": [
            {"turn_index": 1, "matched_node_ids": ["ask_bran_about_tension"]},
            {"turn_index": 6, "matched_node_ids": ["ask_bran_bridge"]},
            {"turn_index": 8, "matched_node_ids": ["report_findings_to_bran"]},
            {"turn_index": 12, "matched_node_ids": ["ask_alternate_route"]},
        ],
    }

    data = _progression_graph_report_data(summary)
    ordered_ids = [node["node_id"] for node in data["nodes"][:4]]

    assert ordered_ids == [
        "ask_bran_about_tension",
        "ask_bran_bridge",
        "report_findings_to_bran",
        "ask_alternate_route",
    ]


def test_progression_graph_report_appends_pending_nodes_after_reached_nodes():
    from tests.rpg.autoplay.campaign_report import _progression_graph_report_data

    summary = {
        "scenario_seed": "tavern_story_seed",
        "scenario_progression_arc_summary": {
            "graph_id": "graph:tavern_story_seed",
            "arc_complete": False,
            "expected_node_count": 18,
            "completed_node_count": 2,
            "completed_node_ids": [
                "ask_bran_about_tension",
                "ask_bran_who_left_side_door",
            ],
            "remaining_node_ids": [
                "ask_bran_direction",
                "ask_mira_side_door",
            ],
        },
        "progression_completed_nodes": {
            "ask_bran_about_tension": {},
            "ask_bran_who_left_side_door": {},
        },
        "scenario_progression_log": [
            {"turn_index": 1, "matched_node_ids": ["ask_bran_about_tension"]},
            {"turn_index": 2, "matched_node_ids": ["ask_bran_who_left_side_door"]},
        ],
    }

    data = _progression_graph_report_data(summary)
    ordered_ids = [node["node_id"] for node in data["nodes"]]

    assert ordered_ids[0] == "ask_bran_about_tension"
    assert ordered_ids[1] == "ask_bran_who_left_side_door"
    assert "ask_bran_direction" in ordered_ids[2:]
    assert "ask_mira_side_door" in ordered_ids[2:]
