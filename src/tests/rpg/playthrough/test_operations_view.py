"""The operations view (RQ-8.4): each turn's class, failure, degraded stages, time and model calls, by day."""
from __future__ import annotations

import pytest

from tests.rpg.playthrough.campaigns import POSTGRES

pytestmark = POSTGRES


def _today(play) -> dict:
    body = play.client.get("/api/rpg/operations", params={"days": 1}).json()
    assert body["ok"] is True
    [today] = body["days"]
    return today


def test_the_turns_played_are_counted_by_class_with_their_time_and_calls(launch, monkeypatch) -> None:
    from app.apps.rpg.edge.api.turn_pipeline import submit_rpg_turn
    from app.apps.rpg.session import pipeline

    play = launch("aurelia")
    before = play.client.get("/api/rpg/operations", params={"days": 1}).json()["days"]
    counted = before[0]["turns"] if before else 0
    failed = before[0]["failed"] if before else 0
    play.turn("look around")
    play.turn("wait")
    today = _today(play)
    assert today["turns"] == counted + 2 and today["failed"] == failed
    classes = {row["turn_class"]: row for row in today["classes"]}
    assert {"look", "wait"} <= set(classes) and classes["wait"]["p50_ms"] > 0
    assert today["model_calls"] >= 1  # the look is narrated; waiting asks no model

    # A turn that breaks is a failure; one the game refuses is not.
    def broken(*args, **kwargs):
        raise RuntimeError("the turn broke")

    monkeypatch.setattr(pipeline, "apply_turn", broken)
    with pytest.raises(RuntimeError):
        submit_rpg_turn(session_id=play.session_id, command="look around", submission_id="ops-broken", source="test")
    monkeypatch.undo()
    refused = submit_rpg_turn(session_id="no-such-campaign", command="look around", submission_id="ops-refused",
                              source="test")
    assert refused["status_code"] == 404
    after = _today(play)
    assert after["failed"] == today["failed"] + 1 and after["turns"] == today["turns"] + 1
    assert after["failure_rate"] == pytest.approx(after["failed"] / after["turns"], abs=1e-4)
