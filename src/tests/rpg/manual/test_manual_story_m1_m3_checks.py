from app.rpg.lore.state import reveal_lore_to_player, upsert_lore_entry
from app.rpg.story_arcs.state import start_story_arc
from tests.rpg.manual.story_m1_m3_checks import run_story_m1_m3_checks


def test_manual_lore_check_reads_session_state():
    session = {"simulation_state": {}}
    upsert_lore_entry(
        session["simulation_state"],
        {"lore_id": "lore:red_sashes", "title": "The Red Sashes"},
    )
    reveal_lore_to_player(session["simulation_state"], "lore:red_sashes")

    result = run_story_m1_m3_checks(
        checks=[
            {
                "type": "lore_condition",
                "condition": {
                    "type": "lore_revealed_to_player",
                    "lore_id": "lore:red_sashes",
                },
                "expected_ok": True,
            }
        ],
        result={},
        session=session,
    )[0]

    assert result["ok"] is True


def test_manual_story_arc_check_reads_session_state():
    session = {"simulation_state": {}}
    start_story_arc(
        session["simulation_state"],
        "arc:bandit_pressure",
        stage="rumors",
        pressure=20,
    )

    result = run_story_m1_m3_checks(
        checks=[
            {
                "type": "story_arc",
                "arc_id": "arc:bandit_pressure",
                "expected": {"stage": "rumors", "pressure": 20},
            }
        ],
        result={},
        session=session,
    )[0]

    assert result["ok"] is True