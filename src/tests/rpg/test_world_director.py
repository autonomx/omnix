from __future__ import annotations

from app.rpg.world_director import (
    DirectorState,
    StoryArc,
    advance_arc,
    apply_pacing_pressure,
    detect_director_loops,
    director_report_payload,
    grounded_director_suggestions,
)


def test_detects_location_action_npc_loops() -> None:
    state = DirectorState(
        recent_locations=("tavern", "tavern", "tavern"),
        recent_npcs=("bran", "bran", "bran"),
        recent_actions=("look", "look", "look"),
    )

    assert [report.kind for report in detect_director_loops(state)] == ["location_loop", "npc_loop", "action_loop"]


def test_pacing_pressure_increases_on_loop() -> None:
    state = DirectorState(arcs=(StoryArc("bandits", "Bandits"),), recent_actions=("look", "look", "look"))
    updated = apply_pacing_pressure(state)

    assert updated.arcs[0].pressure > state.arcs[0].pressure


def test_grounded_suggestions_include_arcs_and_valid_actions() -> None:
    state = DirectorState(arcs=(StoryArc("bandits", "Bandits", threat="Find the quarry"),))
    suggestions = grounded_director_suggestions(state, ["check map"])

    assert suggestions[0] == "Address Bandits: Find the quarry"
    assert "check map" in suggestions


def test_advance_arc_is_pure() -> None:
    state = DirectorState(arcs=(StoryArc("bandits", "Bandits"),))
    updated = advance_arc(state, "bandits", 2)

    assert state.arcs[0].beats_completed == 0
    assert updated.arcs[0].beats_completed == 2


def test_director_report_payload() -> None:
    state = DirectorState(arcs=(StoryArc("bandits", "Bandits"),), recent_actions=("look", "look", "look"))
    payload = director_report_payload(state, ["open journal"])

    assert payload["active_arcs"] == ["bandits"]
    assert payload["loops"][0]["kind"] == "action_loop"
    assert payload["suggested_actions"]
