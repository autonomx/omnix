"""Playthrough: checks outside a fight (RQ-5.2; docs/rpg/design/checks.md)."""
from __future__ import annotations

import re

from tests.rpg.playthrough.campaigns import POSTGRES

pytestmark = POSTGRES
ROLL = re.compile(r"d20 (\d+) ([+-]) (\d+) = (\d+) against (\d+), (a strong success|a success|a success at a cost|a failure)")
BANDS = {"a strong success": "strong", "a success": "success", "a success at a cost": "cost", "a failure": "failure"}
PERSUADED = {"strong": 10, "success": 5, "cost": 2, "failure": -5}


def _rolled(text: str) -> tuple[int, int, int, int, str]:
    natural, sign, bonus, total, difficulty, band = ROLL.search(text).groups()
    assert int(total) == int(natural) + (int(bonus) if sign == "+" else -int(bonus))
    return int(natural), int(total), int(difficulty), int(total) - int(difficulty), BANDS[band]


def test_a_check_is_a_visible_roll_whose_band_decides_what_follows(launch) -> None:
    play = launch("aurelia")
    persuaded = play.turn("I try to persuade Liora Fen to show me the way through the gate.")
    _, _, difficulty, _, band = _rolled(play.model.told())  # the roll, as the narrator is told it
    last = play.simulation()["checks"]["last"]
    assert (last["kind"], last["target_id"], last["band"], last["difficulty"]) == ("persuade", "npc:liora-fen", band, 13)
    assert play.simulation()["relationship_state"]["npc:liora-fen"]["trust"] == PERSUADED[band]
    assert persuaded["outcome"]["planned_action"] == "check"
    if band in {"strong", "success"}:
        assert play.player_state()["skills"]["persuasion"]["xp"] > 0  # a success teaches
    again = play.turn("I try to persuade Liora Fen to show me the way through the gate.")
    assert _rolled(play.model.told())[2] == difficulty + 2  # the same try again, here, is harder

    lore = play.turn("I try to recall what I know about the Echo Wolf.")
    told = play.model.told()
    if _rolled(told)[4] in {"strong", "success"}:
        assert "Its weakness: bells, contradictory commands." in told
    searched = play.turn("I search the undergrowth carefully")  # "search the area": exploring (EV-10)
    assert play.simulation()["checks"]["last"]["kind"] == "search" and searched["outcome"]["planned_action"] == "check"
    assert len(play.simulation()["checks"]["history"]) == 4
    assert lore and again
