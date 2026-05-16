from tests.rpg.autoplay_llm_campaign import _direct_complete_graph_action_from_command


def test_report_findings_about_ambush_does_not_grant_xp():
    result = _direct_complete_graph_action_from_command(
        command="I report to Bran that the trail points to an ambush.",
        row={
            "turn_index": 22,
            "player_action": "I report to Bran that the trail points to an ambush.",
        },
        all_graph_actions=[
            {
                "action_id": "report_findings_to_bran",
                "command": "I report to Bran that the trail points to an ambush.",
                "mechanic": "report",
                "mechanics": ["report", "faction_consequence", "npc_reaction"],
                "changed_parts": ["report", "faction_consequence", "npc_reaction"],
                "action_terms": ["report", "bran", "ambush", "evidence"],
            }
        ],
        completed_action_ids=set(),
        completed_mechanics=set(),
    )

    assert result["completed"] is True
    assert result.get("xp_execution_applied") is False

    row = result["row"]

    assert "xp_delta" not in row.get("state_delta", {})
    assert "combat_result" not in row.get("result", {})
    assert not row.get("direct_graph_xp_execution_applied")


def test_choose_ambush_response_does_not_grant_xp_without_explicit_combat_action_id():
    result = _direct_complete_graph_action_from_command(
        command="I choose the safest response to the ambush signs.",
        row={
            "turn_index": 23,
            "player_action": "I choose the safest response to the ambush signs.",
        },
        all_graph_actions=[
            {
                "action_id": "choose_ambush_response",
                "command": "I choose the safest response to the ambush signs.",
                "mechanic": "story_choice",
                "mechanics": ["story_choice", "faction_consequence"],
                "changed_parts": ["story_choice", "faction_consequence"],
                "action_terms": ["choose", "ambush", "response"],
            }
        ],
        completed_action_ids=set(),
        completed_mechanics=set(),
    )

    assert result["completed"] is True
    assert result.get("xp_execution_applied") is False

    row = result["row"]

    assert "xp_delta" not in row.get("state_delta", {})
    assert "combat_result" not in row.get("result", {})
