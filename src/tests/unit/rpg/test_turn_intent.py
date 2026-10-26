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


def test_what_the_model_reads_into_a_hypothetical_is_never_done(monkeypatch) -> None:
    from app.apps.rpg.foundation import llm_app_gateway
    from app.apps.rpg.session.turn import intent

    class _Gateway:
        def generate(self, prompt, **_kwargs):
            return ('{"readings": [{"family": "attack", "target_id": "npc:bran", "confidence": 0.95},'
                    ' {"family": "talk", "target_id": "npc:bran", "confidence": 0.6}]}')

    monkeypatch.setattr(llm_app_gateway, "build_app_llm_gateway", lambda: _Gateway())
    read = intent.read_with_model({}, SCENE, "and what would happen if I struck Bran down right now?")
    assert read.reading is not None and read.reading.family == "talk"


def test_a_question_about_a_deed_is_asked_not_done_but_a_request_is_done(monkeypatch) -> None:
    """The route's intent eval: "what does the local news cost?" was read as a purchase, and paid for."""
    from app.apps.rpg.foundation import llm_app_gateway
    from app.apps.rpg.session.turn import intent

    class _Gateway:
        def generate(self, prompt, **_kwargs):
            return ('{"readings": [{"family": "attack", "target_id": "npc:bran", "confidence": 0.95},'
                    ' {"family": "talk", "target_id": "npc:bran", "confidence": 0.6}]}')

    monkeypatch.setattr(llm_app_gateway, "build_app_llm_gateway", lambda: _Gateway())
    asked = intent.read_with_model({}, SCENE, "should I fight Bran?")
    assert asked.reading is not None and asked.reading.family == "talk"
    requested = intent.read_with_model({}, SCENE, "Bran, can you fight me?")
    assert requested.reading is not None and requested.reading.family == "attack"


def test_a_reading_the_intent_call_chose_is_planned_at_the_models_own_confidence() -> None:
    """The route's intent eval: "examine my knife" read by the model as looking at the Iron Dagger (0.6) was dropped
    by the grammar's bar (0.8) and played as a free action."""
    from app.apps.rpg.rules.intent.grammar import IntentCandidate
    from app.apps.rpg.session.turn.planning import plan_action

    reading = IntentCandidate(family="look", target_id="iron_dagger", target_kind="item", confidence=0.6, reason="model")
    assert plan_action(reading) is None  # the grammar's own reading, unsure: the intent call decides
    planned = plan_action(reading, decided=True)
    assert planned is not None and (planned.mechanic, planned.target_id) == ("look", "iron_dagger")


def test_a_question_about_a_place_elsewhere_is_no_look_at_it(monkeypatch) -> None:
    from app.apps.rpg.foundation import llm_app_gateway
    from app.apps.rpg.rules.intent.grammar import SceneEntity, SceneView
    from app.apps.rpg.session.turn import intent

    scene = SceneView((SceneEntity("npc:bran", "person", ("Bran",), here=True),
                       SceneEntity("loc:pass", "place", ("the pass",), here=False)))

    class _Gateway:
        def generate(self, prompt, **_kwargs):
            return '{"readings": [{"family": "look", "target_id": "loc:pass", "confidence": 0.9}]}'

    monkeypatch.setattr(llm_app_gateway, "build_app_llm_gateway", lambda: _Gateway())
    assert intent.read_with_model({}, scene, "what is the pass like?").reading is None  # asked, not looked at


def test_a_remark_to_no_one_is_said_to_the_room_not_asked_about_or_looked_at(monkeypatch) -> None:
    """The route's intent eval: in the docks, with three people there, "I smile" asked which of two it was for, and
    "such white walls" looked around."""
    from app.apps.rpg.foundation import llm_app_gateway
    from app.apps.rpg.session.turn import intent

    scene = SceneView((SceneEntity("npc:kade", "person", ("Selene Kade", "the doctor"), here=True),
                       SceneEntity("npc:juno", "person", ("Juno Rask", "the union leader"), here=True)))
    replies: list[str] = []

    class _Gateway:
        def generate(self, prompt, **_kwargs):
            return replies.pop(0)

    monkeypatch.setattr(llm_app_gateway, "build_app_llm_gateway", lambda: _Gateway())
    replies.append('{"readings": [{"family": "talk", "target_id": "npc:kade", "confidence": 0.6},'
                   ' {"family": "talk", "target_id": "npc:juno", "confidence": 0.55}]}')
    smiled = intent.read_with_model({}, scene, "I smile", remark=True)
    assert smiled.reading is None and smiled.between is None and not smiled.unavailable  # a free action
    replies.append('{"readings": [{"family": "look", "confidence": 0.7}]}')
    assert intent.read_with_model({}, scene, "Such white walls.", remark=True).reading is None
    replies.append('{"readings": [{"family": "talk", "target_id": "npc:juno", "confidence": 0.9}]}')
    greeted = intent.read_with_model({}, scene, "I greet the union leader", remark=True).reading
    assert greeted is not None and (greeted.family, greeted.target_id) == ("talk", "npc:juno")
    replies.append('{"readings": [{"family": "talk", "target_id": "npc:kade", "confidence": 0.6},'
                   ' {"family": "talk", "target_id": "npc:juno", "confidence": 0.55}]}')
    assert intent.read_with_model({}, scene, "talk to one of them").between is not None  # not a remark: asked
