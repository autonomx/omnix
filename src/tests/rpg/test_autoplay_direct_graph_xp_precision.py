from tests.rpg.autoplay_llm_campaign import (
    _direct_complete_graph_action_from_command,
    _infer_mechanics_from_graph_action,
)


def test_report_ambush_findings_does_not_infer_combat_xp():
    action = {
        "action_id": "report_findings_to_bran",
        "command": "I report to Bran that the traveler's trail points to an ambush.",
        "mechanic": "report",
        "mechanics": ["report", "faction_consequence", "npc_reaction"],
        "action_terms": ["report", "bran", "ambush", "evidence"],
    }

    mechanics = _infer_mechanics_from_graph_action(
        action,
        "I report to Bran that the traveler's trail points to an ambush.",
    )

    assert "combat_resolved" not in mechanics
    assert "xp_gain" not in mechanics

    result = _direct_complete_graph_action_from_command(
        command="I report to Bran that the traveler's trail points to an ambush.",
        row={"turn_index": 8},
        all_graph_actions=[action],
        completed_action_ids=set(),
        completed_mechanics=set(),
    )

    row = result["row"]

    assert "xp_delta" not in row.get("state_delta", {})
    assert "combat_result" not in row.get("result", {})


def test_actual_combat_action_still_grants_xp():
    result = _direct_complete_graph_action_from_command(
        command="I protect the wagon and fight the bandits.",
        row={"turn_index": 16},
        all_graph_actions=[
            {
                "action_id": "protect_wagon_or_lure_bandits",
                "command": "I protect the wagon and fight the bandits.",
                "mechanic": "combat_started",
                "mechanics": ["combat_started", "combat_resolved", "xp_gain"],
                "action_terms": ["protect", "wagon", "fight", "bandits"],
            }
        ],
        completed_action_ids=set(),
        completed_mechanics=set(),
    )

    row = result["row"]

    assert row["state_delta"]["xp_delta"] == 5
    assert row["result"]["combat_result"]["ok"] is True
