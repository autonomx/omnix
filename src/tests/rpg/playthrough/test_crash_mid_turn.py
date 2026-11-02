"""Playthrough: a crash at any step of a turn leaves the committed turn or none, and a retry finishes it once
(RQ-8.5; roadmap §2, P1).

The gateway fails at one step (the request raises there, as a killed process stops there): before the turn's
commit, inside its PostgreSQL transaction after the turn and its narration are written, or after the commit while
the response is built. The campaign then holds the whole turn (its revision, turn row and canonical narration,
committed together) or nothing of it, and the player's client retries with the same submission id: the turn
commits exactly once, and a turn already committed is answered from its record.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest

from tests.rpg.playthrough.campaigns import POSTGRES

pytestmark = POSTGRES


class _Crash(RuntimeError):
    pass


def _crashing_at(step: str, real):
    @contextmanager
    def span(name: str, *args, **kwargs):
        with real(name, *args, **kwargs) as value:
            if name == step:
                raise _Crash(f"the gateway stopped at {step}")
            yield value

    return span


def _crash_in_the_transaction(*_args, **_kwargs):
    raise _Crash("the gateway stopped inside the turn's transaction")


# Where the gateway stops, and whether the turn was committed by then.
STOPS = {
    "turn.apply": False,  # before anything of the turn runs
    "turn.postgresql_commit": False,  # the turn resolved and narrated, not yet written
    "inside the transaction": False,  # written (turn row, narration), the submission not yet completed: rolled back
    "turn.narrative_present": True,  # committed; the presentation that follows the commit
    "turn.narrative_delivery_prepare": True,
    "turn.session_persist": True,
    "turn.response_contract_build": True,  # committed; the answer not yet sent
}


@pytest.mark.parametrize("stop", list(STOPS))
def test_a_crash_at_any_step_leaves_the_turn_or_none_and_a_retry_commits_it_once(launch, monkeypatch, stop) -> None:
    from app.apps.rpg.edge.api import turn_pipeline
    from app.apps.rpg.foundation.persistence.foreground_submission_repository import (
        PostgresForegroundSubmissionRepository,
    )
    from app.apps.rpg.session import interaction_stages

    play = launch("aurelia")
    play.turn("look around")
    revision, turns, rows = play.revision(), play.turn_count(), len(play.turn_rows())

    with monkeypatch.context() as crashing:
        if stop == "inside the transaction":
            crashing.setattr(PostgresForegroundSubmissionRepository, "complete", _crash_in_the_transaction)
        else:
            for module in (turn_pipeline, interaction_stages):
                crashing.setattr(module, "rpg_pipeline_span", _crashing_at(stop, module.rpg_pipeline_span))
        with pytest.raises(_Crash):
            play.post_turn("wait", submission_id="crash-1")

    committed = STOPS[stop]
    assert play.revision() == revision + committed and len(play.turn_rows()) == rows + committed
    assert play.turn_count() == turns + committed  # the document and its turn rows agree: all of it, or none

    retried = play.post_turn("wait", submission_id="crash-1")
    assert retried.status_code == 200, retried.text[:300]
    assert play.revision() == revision + 1 and play.turn_count() == turns + 1  # once, whichever way it went
    turn_rows = play.turn_rows()
    assert len(turn_rows) == rows + 1 and [row["submission_id"] for row in turn_rows].count("crash-1") == 1
    assert retried.json()["visible_response"]["plain_text"]  # the answer is the turn's
