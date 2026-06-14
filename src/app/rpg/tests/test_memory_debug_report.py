"""Tests for deterministic RPG memory debug report helpers."""
from __future__ import annotations

from copy import deepcopy

from app.rpg.ai.memory_narration_grounding import validate_memory_narration_text
from app.rpg.session.memory_actor import write_actor_memory
from app.rpg.session.memory_debug_report import (
    build_memory_debug_report_payload,
    render_memory_debug_report_html,
)
from app.rpg.session.memory_prompt import build_relevant_memory_context
from app.rpg.session.memory_world import write_world_memory
from app.rpg.session.memory_writer import write_post_turn_memory
from tests.rpg import interactive_cli_campaign as cli


def _turn_payload() -> dict:
    return {
        "authoritative": {
            "turn_id": "turn:7",
            "tick": 7,
            "summary": "Bran warns the player about the quarry road.",
            "location_id": "rusty_flagon",
            "action_type": "dialogue",
            "npc": {"id": "bran", "line": "Keep your eyes open near the quarry road."},
        }
    }


def _memory_session() -> dict:
    session = {"session_id": "s1", "runtime_state": {}}
    session = write_post_turn_memory(
        session,
        _turn_payload(),
        player_input="I ask Bran about the road.",
    )
    session = write_actor_memory(
        session,
        actor_id="bran",
        text="Bran remembers that the player paid for stew without haggling.",
        location_id="rusty_flagon",
        tags=["stew", "commerce"],
    )
    return write_world_memory(
        session,
        text="A rumor spreads in the Rusty Flagon about lights near the quarry road.",
        event_type="rumor",
        scope="location",
        scope_id="rusty_flagon",
        location_id="rusty_flagon",
        tags=["quarry", "rumor"],
    )


def _raw_result() -> dict:
    session = _memory_session()
    relevant_memory = build_relevant_memory_context(
        session,
        player_input="Bran, do you remember the stew and quarry?",
        actor_ids=["bran"],
        location_id="rusty_flagon",
    )
    validation = validate_memory_narration_text(
        "Bran remembers that the player paid for stew without haggling.",
        {
            "runtime_state": session["runtime_state"],
            "simulation_state": {"player_state": {"location_id": "rusty_flagon"}},
            "player_input": "Bran, do you remember the stew and quarry?",
            "turn_contract": {
                "interpreted_action": {"target_id": "bran", "target_name": "Bran"},
            },
            "relevant_memory": relevant_memory,
        },
    )
    return {
        "ok": True,
        "narration": "Bran remembers the paid stew.",
        "session": session,
        "first_call_grounding_diagnostics": {
            "turn_grounding_packet": {"relevant_memory": relevant_memory},
        },
        "memory_grounding_validation": validation,
    }


def test_memory_debug_report_summarizes_writes_retrieval_and_grounding():
    turn = {
        "turn_index": 7,
        "player_input": "Bran, do you remember the stew and quarry?",
        "raw_result": _raw_result(),
    }

    report = build_memory_debug_report_payload(turn)

    assert report["format_version"] == "rpg_memory_debug_report_v1"
    assert report["available"] is True
    assert report["memory_state"]["total_entries"] == 4
    assert report["memory_state"]["by_kind"] == {
        "actor": 1,
        "dialogue": 1,
        "turn": 1,
        "world": 1,
    }
    assert [entry["id"] for entry in report["memory_state"]["recent_writes"]] == [
        "mem:000001",
        "mem:000002",
        "mem:000003",
        "mem:000004",
    ]
    assert report["retrieval"]["counts"] == {"recent": 2, "actors": 1, "world": 1}
    assert "mem:000003" in report["retrieval"]["ids"]
    assert report["grounding"]["ok"] is True
    assert report["grounding"]["memory_ids"] == [
        "mem:000001",
        "mem:000002",
        "mem:000003",
        "mem:000004",
    ]
    assert any("paid for stew" in entry["text"] for entry in report["grounding"]["used_facts"])


def test_memory_debug_report_missing_data_is_empty_and_does_not_mutate():
    turn = {"turn_index": 1, "player_input": "look", "raw_result": {"ok": True}}
    original = deepcopy(turn)

    report = build_memory_debug_report_payload(turn)

    assert report["available"] is False
    assert report["memory_state"]["total_entries"] == 0
    assert report["retrieval"]["entries"] == []
    assert report["grounding"]["used_facts"] == []
    assert turn == original


def test_memory_debug_report_renders_campaign_html_panel():
    turn = {
        "turn_index": 7,
        "player_input": "Bran, do you remember the stew and quarry?",
        "raw_result": _raw_result(),
        "raw_narration": "Bran remembers the paid stew.",
        "scenario_warnings": [],
        "regression_warnings": [],
    }
    summary = cli.build_interactive_campaign_summary(
        run_id="memory-debug",
        session_id="s1",
        requested_turns=1,
        turns=[turn],
        started_at=100.0,
        ended_at=101.0,
        stop_reason="turn_limit",
    )

    html = cli.render_interactive_campaign_html(summary, [turn])
    direct_panel = render_memory_debug_report_html(build_memory_debug_report_payload(turn))
    survival_row = cli._turn_report_row(turn)

    assert "RPG memory debug" in html
    assert "Memory writes" in html
    assert "Retrieved memory" in html
    assert "Grounding used facts" in html
    assert "mem:000003" in html
    assert "paid for stew" in direct_panel
    assert survival_row["memory_debug_report"]["available"] is True
