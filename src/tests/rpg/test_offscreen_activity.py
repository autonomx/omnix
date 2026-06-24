from __future__ import annotations

from app.rpg.offscreen_activity import (
    NpcScheduleEntry,
    OffscreenActivityState,
    day_part_for_turn,
    generate_offscreen_events,
    offscreen_report_payload,
    public_hints_for_location,
    schedule_by_npc,
)


def _state() -> OffscreenActivityState:
    return OffscreenActivityState(
        schedule=(
            NpcScheduleEntry("bran", "morning", "tavern", "works the common room", "Bran is at the tavern most mornings."),
            NpcScheduleEntry("elara", "morning", "market", "checks stock", "Elara opens her stall early."),
            NpcScheduleEntry("bran", "night", "tavern", "closes the taproom", "The tavern grows quiet late."),
        )
    )


def test_day_part_for_turn_is_deterministic() -> None:
    assert [day_part_for_turn(turn) for turn in (0, 6, 12, 18, 24)] == [
        "morning",
        "afternoon",
        "evening",
        "night",
        "morning",
    ]


def test_generate_events_from_schedule() -> None:
    events = generate_offscreen_events(_state(), turn=0)

    assert [event.npc_id for event in events] == ["bran", "elara"]
    assert events[0].visibility == "hidden"
    assert events[0].event_id == "offscreen:0:bran:tavern"


def test_reveal_event_moves_it_to_known_log() -> None:
    state = _state().with_events(generate_offscreen_events(_state(), turn=0))
    revealed = state.reveal_event("offscreen:0:bran:tavern", method="rumor", public_summary="Travelers saw Bran at work.")

    assert len(revealed.hidden_events) == 1
    assert len(revealed.known_events) == 1
    assert "discovered:rumor" in revealed.known_events[0].tags


def test_public_hints_and_report_payload() -> None:
    state = _state().with_events(generate_offscreen_events(_state(), turn=0))

    assert public_hints_for_location(state, "market") == ("Elara opens her stall early.",)
    assert offscreen_report_payload(state)["hidden_count"] == 2


def test_schedule_by_npc_groups_entries() -> None:
    grouped = schedule_by_npc(_state().schedule)

    assert sorted(grouped) == ["bran", "elara"]
    assert len(grouped["bran"]) == 2
