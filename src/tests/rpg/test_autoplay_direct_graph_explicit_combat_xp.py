from tests.rpg.autoplay_llm_campaign import (
    _build_character_inventory_progression_summary,
    _direct_complete_graph_action_from_command,
    _apply_explicit_combat_xp_direct_graph_execution,
)


def test_explicit_combat_direct_graph_completion_grants_xp_state_result_and_display():
    result = _direct_complete_graph_action_from_command(
        command="I protect the wagon and fight the bandits.",
        row={
            "turn_index": 21,
            "player_action": "I protect the wagon and fight the bandits.",
        },
        all_graph_actions=[
            {
                "action_id": "protect_wagon_or_lure_bandits",
                "command": "I protect the wagon and fight the bandits.",
                "mechanic": "combat_started",
                "mechanics": ["combat_started", "combat_resolved", "xp_gain"],
                "changed_parts": ["combat_started", "combat_resolved", "xp_gain"],
                "action_terms": ["protect", "wagon", "fight", "bandits"],
            }
        ],
        completed_action_ids=set(),
        completed_mechanics=set(),
    )

    assert result["completed"] is True
    assert result["execution_applied"] is True
    assert result["xp_execution_applied"] is True
    assert result["xp_delta"] == 5

    row = result["row"]

    assert row["state_delta"]["xp_delta"] == 5
    assert row["state_delta"]["combat_started"] is True
    assert row["state_delta"]["combat_resolved"] is True

    assert row["result"]["combat_result"]["ok"] is True
    assert row["result"]["combat_result"]["xp_delta"] == 5

    assert row["direct_graph_xp_execution_applied"] is True
    assert row["direct_graph_xp_execution_action_id"] == "protect_wagon_or_lure_bandits"

    assert "5 xp" in row["narration"].lower()
    assert row["selected_narration"]["reward"]["xp_delta"] == 5


def test_explicit_combat_xp_execution_is_idempotent():
    result = _direct_complete_graph_action_from_command(
        command="I protect the wagon and fight the bandits.",
        row={"turn_index": 21, "player_action": "I protect the wagon and fight the bandits."},
        all_graph_actions=[
            {
                "action_id": "protect_wagon_or_lure_bandits",
                "command": "I protect the wagon and fight the bandits.",
                "mechanic": "combat_started",
                "mechanics": ["combat_started", "combat_resolved", "xp_gain"],
                "changed_parts": ["combat_started", "combat_resolved", "xp_gain"],
                "action_terms": ["protect", "wagon", "fight", "bandits"],
            }
        ],
        completed_action_ids=set(),
        completed_mechanics=set(),
    )

    row = result["row"]

    # Simulate real runner reapplying after dialogue repair and before transcript append.
    row = _apply_explicit_combat_xp_direct_graph_execution(
        row,
        action_id="protect_wagon_or_lure_bandits",
    )

    assert row["state_delta"]["xp_delta"] == 5
    assert row["result"]["combat_result"]["xp_delta"] == 5


def test_character_inventory_progression_reads_explicit_combat_xp_delta():
    result = _direct_complete_graph_action_from_command(
        command="I protect the wagon and fight the bandits.",
        row={
            "turn_index": 21,
            "player_action": "I protect the wagon and fight the bandits.",
        },
        all_graph_actions=[
            {
                "action_id": "protect_wagon_or_lure_bandits",
                "command": "I protect the wagon and fight the bandits.",
                "mechanic": "combat_started",
                "mechanics": ["combat_started", "combat_resolved", "xp_gain"],
                "changed_parts": ["combat_started", "combat_resolved", "xp_gain"],
                "action_terms": ["protect", "wagon", "fight", "bandits"],
            }
        ],
        completed_action_ids=set(),
        completed_mechanics=set(),
    )

    progression = _build_character_inventory_progression_summary(
        [result["row"]],
        initial_state={
            "name": "The Player",
            "currency": {"gold": 15, "silver": 20, "copper": 50},
            "inventory": [],
            "xp": 0,
            "level": 1,
        },
    )

    assert progression["player"]["xp"] == 5
    assert progression["xp_events"]
    assert progression["xp_events"][0]["xp_delta"] == 5


def test_character_inventory_progression_xp_event_uses_visible_player_action():
    result = _direct_complete_graph_action_from_command(
        command="I check in with Garran and focus on the active wagon-road objective.",
        row={
            "turn_index": 19,
            "player_action": "I check in with Garran and focus on the active wagon-road objective.",
        },
        all_graph_actions=[
            {
                "action_id": "protect_wagon_or_lure_bandits",
                "command": "I protect the wagon and fight the bandits.",
                "mechanic": "combat_started",
                "mechanics": ["combat_started", "combat_resolved", "xp_gain"],
                "changed_parts": ["combat_started", "combat_resolved", "xp_gain"],
                "action_terms": ["protect", "wagon", "fight", "bandits"],
            }
        ],
        completed_action_ids=set(),
        completed_mechanics=set(),
    )

    row = result["row"]
    row["direct_graph_action_completion"] = {
        key: value for key, value in result.items() if key != "row"
    }

    from tests.rpg.autoplay_llm_campaign import _apply_direct_graph_display_quality_pass

    row = _apply_direct_graph_display_quality_pass(row)

    progression = _build_character_inventory_progression_summary(
        [row],
        initial_state={
            "name": "The Player",
            "currency": {"gold": 15, "silver": 20, "copper": 50},
            "inventory": [],
            "xp": 0,
            "level": 1,
        },
    )

    assert progression["xp_events"]
    assert progression["xp_events"][0]["xp_delta"] == 5
    assert progression["xp_events"][0]["player_action"] == "I protect the wagon and fight the bandits."
