"""The balance simulation (RQ-5.3's exit; docs/rpg/design/README.md, "Balance bands").

A deterministic reasonable player plays 500 turns of each world on the pipeline's rules (``scripts/rpg_balance_sim``)
and the measures stay inside the bands. The purse and the quests done are, since the world's pressures raise side
quests that pay (RQ-5.4). The win rate is not yet: a world's bestiary is fixed, so the hero outclasses it and nearly
every late fight is won, and in the starter world, whose quests near town hunt rats and bandits, every early one too
(encounters that rise with the hero are RQ-5.6's).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.rpg.playthrough.campaigns import POSTGRES

pytestmark = POSTGRES
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts"))
PENDING = {"500 turns, win_rate": "RQ-5.6: encounters that rise with the hero"}
PENDING_IN = {"starter": {"100 turns, win_rate": "RQ-5.6: the quests near town hunt creatures the hero soon outgrows"}}


def _report(launch, world: str) -> dict:
    from rpg_balance_sim import simulate

    from app.apps.rpg.session.service import load_session

    return simulate(load_session(launch(world).session_id), turns=500)


@pytest.mark.parametrize("world", ["aurelia", "starter"])
def test_a_reasonable_player_stays_inside_the_progression_bands(launch, world) -> None:
    from rpg_balance_sim import outside

    report = _report(launch, world)
    pending = {**PENDING, **PENDING_IN.get(world, {})}
    broken = [line for line in outside(report) if not any(key in line for key in pending)]
    assert broken == [], report
    assert report[500]["unplanned"] == 0  # every command the player gives, the pipeline plays


@pytest.mark.xfail(strict=True, reason="; ".join(PENDING.values()))
def test_the_late_win_rate_stays_inside_its_band(launch) -> None:
    from rpg_balance_sim import outside

    assert [line for line in outside(_report(launch, "aurelia")) if any(key in line for key in PENDING)] == []
