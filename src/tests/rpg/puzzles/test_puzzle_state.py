from app.rpg.puzzles.state import (
    get_puzzle,
    set_puzzle_flag,
    set_puzzle_state,
    start_puzzle,
)


def test_start_puzzle_sets_active_state():
    simulation_state = {}
    result = start_puzzle(
        simulation_state,
        "puzzle:cellar_runes",
        title="Cellar Runes",
        state="initial",
    )

    puzzle = get_puzzle(simulation_state, "puzzle:cellar_runes")
    assert result["ok"] is True
    assert puzzle["status"] == "active"
    assert puzzle["state"] == "initial"


def test_set_puzzle_state_can_solve():
    simulation_state = {}
    start_puzzle(simulation_state, "puzzle:cellar_runes")
    result = set_puzzle_state(
        simulation_state,
        "puzzle:cellar_runes",
        "solved",
        status="solved",
        turn_index=3,
    )

    assert result["ok"] is True
    assert result["puzzle"]["status"] == "solved"
    assert result["puzzle"]["solved_turn"] == 3


def test_set_puzzle_flag():
    simulation_state = {}
    set_puzzle_flag(simulation_state, "puzzle:cellar_runes", "rune_a_lit", True)

    puzzle = get_puzzle(simulation_state, "puzzle:cellar_runes")
    assert puzzle["flags"]["rune_a_lit"] is True