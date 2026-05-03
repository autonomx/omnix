from app.rpg.story_arcs.state import start_story_arc
from app.rpg.story_events.application import apply_story_event
from tests.rpg.manual.story_event_m4_m6_checks import run_story_event_m4_m6_checks


def test_manual_story_event_check_reads_applied_event_from_session():
    session = {"simulation_state": {}}
    start_story_arc(session["simulation_state"], "arc:bandit_pressure")
    apply_story_event(
        session["simulation_state"],
        {
            "event_id": "event:test_applied",
            "arc_id": "arc:bandit_pressure",
            "effects": [],
        },
    )

    result = run_story_event_m4_m6_checks(
        checks=[
            {"type": "story_event_applied", "event_id": "event:test_applied"}
        ],
        result={},
        session=session,
    )[0]

    assert result["ok"] is True


def test_manual_story_event_validation_check():
    session = {"simulation_state": {}}
    start_story_arc(session["simulation_state"], "arc:bandit_pressure")

    result = run_story_event_m4_m6_checks(
        checks=[
            {
                "type": "story_event_validation",
                "expected_ok": False,
                "event": {
                    "event_id": "event:invalid",
                    "arc_id": "arc:bandit_pressure",
                    "effects": [{"type": "invent_gold"}],
                },
            }
        ],
        result={},
        session=session,
    )[0]

    assert result["ok"] is True
    assert result["validation"]["ok"] is False