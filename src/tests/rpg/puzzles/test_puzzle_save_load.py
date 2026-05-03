import json

from app.rpg.puzzles.state import normalize_puzzle_state, set_puzzle_flag, start_puzzle


def test_puzzle_state_json_roundtrip():
    simulation_state = {}
    start_puzzle(simulation_state, "puzzle:cellar_runes", state="initial")
    set_puzzle_flag(simulation_state, "puzzle:cellar_runes", "rune_unlocked", True)

    encoded = json.dumps(simulation_state["puzzle_state"], sort_keys=True)
    decoded = json.loads(encoded)
    normalized = normalize_puzzle_state(decoded)

    puzzle = normalized["puzzles"]["puzzle:cellar_runes"]
    assert puzzle["state"] == "initial"
    assert puzzle["flags"]["rune_unlocked"] is True