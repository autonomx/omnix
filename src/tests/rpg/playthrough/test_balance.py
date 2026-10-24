"""The balance simulation (RQ-5.3's exit; docs/rpg/design/README.md, "Balance bands").

A deterministic reasonable player plays 500 turns of each world on the pipeline's rules (``scripts/rpg_balance_sim``)
and the measures stay inside the bands: since the world's pressures raise side quests that pay (RQ-5.4) and creatures
act like themselves (flee when hurt, call allies, keep their post: RQ-5.6). Two are not yet, each tracked as a strict
expected failure: in Aurelia, once the hero has made their region's roads safe nothing pays (creatures carry no coin,
sources and sinks are RQ-5.5's), and in the starter world the first quests hunt rats and lone bandits, so every early
fight is won.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.rpg.playthrough.campaigns import POSTGRES

pytestmark = POSTGRES
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts"))
PENDING = {"aurelia": {"500 turns, purse": "RQ-5.5: once the hero's region is safe, nothing pays"},
           "starter": {"100 turns, win_rate": "the first quests hunt creatures far below the hero"}}


def _report(launch, world: str) -> dict:
    from rpg_balance_sim import simulate

    from app.apps.rpg.session.service import load_session

    return simulate(load_session(launch(world).session_id), turns=500)


@pytest.mark.parametrize("world", ["aurelia", "starter"])
def test_a_reasonable_player_stays_inside_the_progression_bands(launch, world) -> None:
    from rpg_balance_sim import outside

    report = _report(launch, world)
    broken = [line for line in outside(report) if not any(key in line for key in PENDING[world])]
    assert broken == [], report
    assert report[500]["unplanned"] == 0  # every command the player gives, the pipeline plays


@pytest.mark.parametrize("world", sorted(PENDING))
def test_what_is_pending_is_still_outside_its_band(launch, world) -> None:
    """Strict: when a pending measure comes inside its band, this fails, and it leaves the pending list."""
    from rpg_balance_sim import outside

    lines = outside(_report(launch, world))
    assert all(any(key in line for line in lines) for key in PENDING[world]), (PENDING[world], lines)
