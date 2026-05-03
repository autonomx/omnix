from app.rpg.puzzles.state import get_puzzle, start_puzzle
from app.rpg.puzzles.transitions import apply_puzzle_transition


def test_wrong_input_does_not_advance():
    simulation_state = {}
    start_puzzle(simulation_state, "puzzle:cellar_runes", state="initial")
    result = apply_puzzle_transition(
        simulation_state,
        {
            "action": "input",
            "puzzle_id": "puzzle:cellar_runes",
            "expected_input": "moon",
            "input": "sun",
            "next_state": "rune_unlocked",
        },
    )

    puzzle = get_puzzle(simulation_state, "puzzle:cellar_runes")
    assert result["ok"] is False
    assert result["reason"] == "wrong_input"
    assert puzzle["state"] == "initial"


def test_correct_input_advances_state_and_sets_flag():
    simulation_state = {}
    start_puzzle(simulation_state, "puzzle:cellar_runes", state="initial")
    result = apply_puzzle_transition(
        simulation_state,
        {
            "action": "input",
            "puzzle_id": "puzzle:cellar_runes",
            "expected_input": "moon",
            "input": "moon",
            "next_state": "rune_unlocked",
            "set_flags": {"rune_unlocked": True},
        },
    )

    puzzle = get_puzzle(simulation_state, "puzzle:cellar_runes")
    assert result["ok"] is True
    assert puzzle["state"] == "rune_unlocked"
    assert puzzle["flags"]["rune_unlocked"] is True


def test_puzzle_requires_prior_flag():
    simulation_state = {}
    start_puzzle(simulation_state, "puzzle:cellar_runes", state="initial")
    result = apply_puzzle_transition(
        simulation_state,
        {
            "action": "solve",
            "puzzle_id": "puzzle:cellar_runes",
            "conditions": [
                {
                    "type": "puzzle_flag",
                    "puzzle_id": "puzzle:cellar_runes",
                    "flag": "rune_unlocked",
                    "expected": True,
                }
            ],
        },
    )

    assert result["ok"] is False
    assert result["reason"] == "conditions_failed"