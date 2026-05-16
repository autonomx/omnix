from tests.rpg.autoplay_llm_campaign import (
    _direct_complete_graph_action_from_command,
    _strip_combat_mechanics_from_noncombat_direct_graph_row,
)


def test_noncombat_report_action_strips_combat_mechanics():
    row = _strip_combat_mechanics_from_noncombat_direct_graph_row(
        {
            "direct_graph_action_completion": {
                "action_id": "report_findings_to_bran",
                "mechanics": ["report", "combat_started", "combat_resolved", "xp_gain"],
                "changed_parts": ["report", "combat_started", "combat_resolved", "xp_gain"],
            },
            "mechanics_covered_this_turn": ["report", "combat_started", "xp_gain"],
            "direct_graph_changed_parts": ["report", "combat_resolved"],
            "fired_hooks": [
                {
                    "kind": "graph_direct_completion",
                    "mechanics": ["report", "combat_started", "xp_gain"],
                    "changed_parts": ["report", "combat_resolved"],
                    "effects": {
                        "flags": {
                            "mechanic:report": True,
                            "mechanic:combat_started": True,
                            "mechanic:xp_gain": True,
                        }
                    },
                }
            ],
        }
    )

    direct = row["direct_graph_action_completion"]

    assert "combat_started" not in direct["mechanics"]
    assert "combat_resolved" not in direct["changed_parts"]
    assert "xp_gain" not in row["mechanics_covered_this_turn"]
    assert row["direct_graph_noncombat_mechanics_cleanup_applied"] is True

    hook = row["fired_hooks"][0]
    assert "combat_started" not in hook["mechanics"]
    assert "mechanic:combat_started" not in hook["effects"]["flags"]
    assert "mechanic:xp_gain" not in hook["effects"]["flags"]


def test_explicit_combat_action_keeps_combat_mechanics():
    row = _strip_combat_mechanics_from_noncombat_direct_graph_row(
        {
            "direct_graph_action_completion": {
                "action_id": "protect_wagon_or_lure_bandits",
                "mechanics": ["combat_started", "combat_resolved", "xp_gain"],
                "changed_parts": ["combat_started", "combat_resolved", "xp_gain"],
            }
        }
    )

    direct = row["direct_graph_action_completion"]

    assert "combat_started" in direct["mechanics"]
    assert "xp_gain" in direct["changed_parts"]
    assert not row.get("direct_graph_noncombat_mechanics_cleanup_applied")


def test_later_noncombat_action_ids_strip_combat_mechanics():
    for action_id in (
        "return_to_allies_with_voss_proof",
        "counter_voss_intimidation",
        "detect_safehouse_watchers",
        "prepare_safehouse_defense",
        "scout_east_road_pressure_points",
        "scout_ridge_hideout",
    ):
        row = _strip_combat_mechanics_from_noncombat_direct_graph_row(
            {
                "direct_graph_action_completion": {
                    "action_id": action_id,
                    "mechanics": ["faction_consequence", "combat_started", "combat_resolved", "xp_gain"],
                    "changed_parts": ["npc_reaction", "combat_started", "combat_resolved", "xp_gain"],
                },
                "mechanics_covered_this_turn": ["faction_consequence", "combat_started", "xp_gain"],
                "direct_graph_changed_parts": ["npc_reaction", "combat_resolved"],
            }
        )

        direct = row["direct_graph_action_completion"]
        assert "combat_started" not in direct["mechanics"]
        assert "combat_resolved" not in direct["changed_parts"]
        assert "xp_gain" not in row["mechanics_covered_this_turn"]


def test_direct_completion_return_strips_noncombat_combat_metadata_before_attach():
    result = _direct_complete_graph_action_from_command(
        command="I scout the ridge hideout.",
        row={
            "turn_index": 95,
            "player_action": "I scout the ridge hideout.",
        },
        all_graph_actions=[
            {
                "action_id": "scout_ridge_hideout",
                "command": "I scout the ridge hideout.",
                "mechanic": "investigation",
                "mechanics": ["investigation", "combat_started", "combat_resolved", "xp_gain"],
                "changed_parts": ["investigation", "combat_started", "combat_resolved", "xp_gain"],
                "action_terms": ["scout", "ridge", "hideout"],
            }
        ],
        completed_action_ids=set(),
        completed_mechanics=set(),
    )

    assert result["completed"] is True
    assert "combat_started" not in result["mechanics"]
    assert "combat_resolved" not in result["changed_parts"]
    assert "xp_gain" not in result["completed_parts"]
    assert not result.get("xp_execution_applied")
