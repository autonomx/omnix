from app.rpg.puzzles.state import set_puzzle_flag, start_puzzle
from app.rpg.quests.state import start_quest
from tests.rpg.manual.quest_puzzle_checks import run_quest_puzzle_checks


def test_manual_quest_check_reads_session_state():
    session = {"simulation_state": {}}
    start_quest(session["simulation_state"], "quest:rat_cellar", stage="started")

    result = run_quest_puzzle_checks(
        checks=[
            {
                "type": "quest_stage",
                "quest_id": "quest:rat_cellar",
                "expected_stage": "started",
                "expected_status": "active",
            }
        ],
        result={},
        session=session,
    )[0]

    assert result["ok"] is True


def test_manual_puzzle_check_reads_session_state():
    session = {"simulation_state": {}}
    start_puzzle(session["simulation_state"], "puzzle:cellar_runes", state="initial")
    set_puzzle_flag(session["simulation_state"], "puzzle:cellar_runes", "rune_unlocked", True)

    result = run_quest_puzzle_checks(
        checks=[
            {
                "type": "puzzle_flag",
                "puzzle_id": "puzzle:cellar_runes",
                "flag": "rune_unlocked",
                "expected": True,
            }
        ],
        result={},
        session=session,
    )[0]

    assert result["ok"] is True