"""The journal is the hero's own account of the day: the game's lines in the first person (RQ-7.1)."""
from __future__ import annotations

from app.apps.rpg.narration.campaign_journal_runtime import _first_person, advance_campaign_journal_for_turn


def test_the_games_lines_become_the_heros_own() -> None:
    assert _first_person("You break away; a parting blow follows you. You escape; the fight yields you nothing.") == (
        "I break away; a parting blow follows me. I escape; the fight yields me nothing.")
    assert _first_person("Your wound closes. You are rested.") == "My wound closes. I am rested."


def test_a_days_entry_tells_what_happened_not_what_was_typed() -> None:
    runtime: dict = {}
    for turn, (typed, told) in enumerate((
        ("go to Starfall Village", "You travel to Starfall Village; the road takes 20 minutes."),
        ("attack the echo wolf", "You hit the Echo Wolf for 3 (7 of 10 left). The Echo Wolf hits you for 2 (98 of 100 left)."),
    ), start=1):
        runtime = advance_campaign_journal_for_turn(
            runtime_state=runtime, turn_index=turn, player_input=typed,
            turn_contract={"player_input": typed, "resolved_result": {"summary": told}})
    entry = runtime["player_journal"]["entries"][-1]
    assert entry["text"] == ("I travel to Starfall Village; the road takes 20 minutes. I hit the Echo Wolf for 3 "
                             "(7 of 10 left). The Echo Wolf hits me for 2 (98 of 100 left).")
    assert "go to" not in entry["text"]
