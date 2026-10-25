"""The intent call, when the grammar is not sure (RQ-3.2; session/turn/intent.py): its readings are checked against
the scene, the best is planned, two close ones are asked between, and none left is a free action."""
from __future__ import annotations

from app.apps.rpg.rules.intent.grammar import IntentCandidate, SceneEntity, SceneView
from app.apps.rpg.session.turn.intent import decide, valid_readings
from app.apps.rpg.session.turn.run import command_for

SCENE = SceneView((SceneEntity("npc:bran", "person", ("Bran",), here=True),
                   SceneEntity("loc:mill", "place", ("Old Mill",), here=True),
                   SceneEntity("item:rope", "item", ("Rope",))))


def test_a_reading_is_kept_only_when_the_planner_can_carry_it_out() -> None:
    rows = [{"family": "talk", "target_id": "npc:bran", "confidence": 0.9},
            {"family": "talk", "target_id": "npc:ghost", "confidence": 0.95},  # no one by that id is here
            {"family": "move", "target_id": "npc:bran", "confidence": 0.8},  # a person is no place to go
            {"family": "fly", "confidence": 1.0},  # no family the pipeline runs
            {"family": "check", "check": "persuade", "target_id": "npc:bran", "confidence": 0.7},
            {"family": "check", "check": "teleport", "confidence": 0.9}]  # no such check
    kept = valid_readings(rows, SCENE)
    assert [(reading.family, reading.target_id, reading.reason) for reading in kept] == [
        ("talk", "npc:bran", "model_reading"), ("check", "npc:bran", "check:persuade")]


def test_the_best_is_planned_two_close_ones_are_asked_between_and_none_is_a_free_action() -> None:
    talk = IntentCandidate(family="talk", target_id="npc:bran", target_kind="person", confidence=0.9)
    go = IntentCandidate(family="move", target_id="loc:mill", target_kind="place", confidence=0.85)
    assert decide([talk, go]).between == (talk, go)  # within 0.15
    far = IntentCandidate(family="move", target_id="loc:mill", target_kind="place", confidence=0.5)
    assert decide([talk, far]).reading == talk
    assert decide([IntentCandidate(family="talk", target_id="npc:bran", confidence=0.3)]).reading is None
    assert decide([]).reading is None and decide([]).between is None
    assert [command_for(reading, SCENE) for reading in (talk, go)] == ["Talk to Bran", "go to Old Mill"]
