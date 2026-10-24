"""The balance simulation (RQ-5.3's exit; docs/rpg/design/README.md, "Balance bands").

A deterministic reasonable player plays 500 turns of each world on the pipeline's rules (``scripts/rpg_balance_sim``)
and the measures stay inside the bands. Three are not yet: the worlds author a few quests and creatures that carry
nothing, so the purse drains once the quests are done (sources and sinks are RQ-5.5's, side quests from the world's
pressures RQ-5.4's), and a world's bestiary is fixed, so by level 8 the hero outclasses it and nearly every late fight
is won (encounters that rise with the hero are RQ-5.6's).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.rpg.playthrough.campaigns import POSTGRES

pytestmark = POSTGRES
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts"))
PENDING = {"purse": "RQ-5.5: no source of coin once the quests are done", "quests_completed": "RQ-5.4: side quests",
           "500 turns, win_rate": "RQ-5.6: encounters that rise with the hero"}


def _report(launch, world: str) -> dict:
    from rpg_balance_sim import simulate

    from app.apps.rpg.session.service import load_session

    return simulate(load_session(launch(world).session_id), turns=500)


@pytest.mark.parametrize("world", ["aurelia", "starter"])
def test_a_reasonable_player_stays_inside_the_progression_bands(launch, world) -> None:
    from rpg_balance_sim import outside

    report = _report(launch, world)
    broken = [line for line in outside(report) if not any(key in line for key in PENDING)]
    assert broken == [], report
    assert report[500]["unplanned"] == 0  # every command the player gives, the pipeline plays


@pytest.mark.xfail(strict=True, reason="; ".join(PENDING.values()))
def test_coin_and_quests_stay_inside_their_bands(launch) -> None:
    from rpg_balance_sim import outside

    assert [line for line in outside(_report(launch, "aurelia")) if any(key in line for key in PENDING)] == []
