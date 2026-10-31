"""The intent call reads every typed line (evolution roadmap EV-9; session/turn/intent.py): its readings and their
slots are checked against the scene, the best is planned, two close ones are asked between, an unclear line gets the
model's question, and none left is a free action."""
from __future__ import annotations

from app.apps.rpg.rules.intent.reading import IntentCandidate, SceneEntity, SceneView
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
    gift = IntentCandidate(family="give", target_id="item:rope", target_kind="item", confidence=0.8)
    assert command_for(gift, SCENE) == "I give the Rope"


def _gateway(monkeypatch, *replies: str) -> None:
    from app.apps.rpg.foundation import llm_app_gateway

    queue = list(replies)

    class _Gateway:
        def generate(self, prompt, **_kwargs):
            return queue.pop(0)

    monkeypatch.setattr(llm_app_gateway, "build_app_llm_gateway", lambda: _Gateway())


def test_a_line_that_asks_or_supposes_is_never_done(monkeypatch) -> None:
    """EV-9: the model says the line asks or supposes ("what would happen if I struck Bran down?"; "should I fight
    Bran?"); then only an answer, the hero's standing or a look at what is here is planned. A request is done."""
    from app.apps.rpg.session.turn import intent

    _gateway(monkeypatch,
             '{"readings": [{"family": "attack", "target_id": "npc:bran", "confidence": 0.95, "asks": true},'
             ' {"family": "talk", "target_id": "npc:bran", "confidence": 0.6, "asks": true}]}',
             '{"readings": [{"family": "attack", "target_id": "npc:bran", "confidence": 0.95}]}')
    asked = intent.read_with_model({}, SCENE, "and what would happen if I struck Bran down right now?")
    assert asked.reading is not None and asked.reading.family == "talk"
    requested = intent.read_with_model({}, SCENE, "Bran, can you fight me?")
    assert requested.reading is not None and requested.reading.family == "attack"


def test_a_reading_the_intent_call_chose_is_planned_at_the_models_own_confidence() -> None:
    """The route's intent eval: "examine my knife" read by the model as looking at the Iron Dagger (0.6) was dropped
    by the grammar's bar (0.8) and played as a free action. EV-9: there is no grammar's bar; every reading planned
    is one the intent call decided, or a card's."""
    from app.apps.rpg.session.turn.planning import plan_action

    reading = IntentCandidate(family="look", target_id="iron_dagger", target_kind="item", confidence=0.6, reason="model")
    planned = plan_action(reading)
    assert planned is not None and (planned.mechanic, planned.target_id) == ("look", "iron_dagger")


def test_a_question_about_a_place_elsewhere_is_no_look_at_it(monkeypatch) -> None:
    from app.apps.rpg.session.turn import intent

    scene = SceneView((SceneEntity("npc:bran", "person", ("Bran",), here=True),
                       SceneEntity("loc:pass", "place", ("the pass",), here=False)))
    _gateway(monkeypatch, '{"readings": [{"family": "look", "target_id": "loc:pass", "confidence": 0.9, "asks": true}]}')
    read = intent.read_with_model({}, scene, "what is the pass like?").reading  # asked, not looked at: Bran is asked
    assert read is not None and (read.family, read.target_id, read.slots.topics) == ("talk", "npc:bran", ("loc:pass",))


def test_a_question_none_of_whose_readings_may_be_done_is_put_to_someone_here(monkeypatch) -> None:
    """The route's intent eval (M2 after EV-9): "what if I punched Liora?" and "who is the Archon?" were read as asked
    deeds and talk with someone away, each under the trusted bar, and played as free actions. They are questions: the
    one named who is here answers, else the one being talked with, else the only person here; with several here and
    none of them named, no one is guessed."""
    from app.apps.rpg.session.turn import intent

    scene = SceneView((SceneEntity("npc:bran", "person", ("Bran",), here=True),
                       SceneEntity("npc:archon", "person", ("the Archon",), here=False)))
    _gateway(monkeypatch,
             '{"readings": [{"family": "talk", "target_id": "npc:archon", "confidence": 0.4, "asks": true},'
             ' {"family": "check", "check": "recall_lore", "target_id": "npc:archon", "confidence": 0.35, "asks": true}]}')
    read = intent.read_with_model({}, scene, "who is the Archon?").reading
    assert read is not None and (read.family, read.target_id, read.slots.topics) == ("talk", "npc:bran", ("npc:archon",))
    assert read.confidence == 0.75  # its readings together
    crowd = SceneView((*scene.entities, SceneEntity("npc:mira", "person", ("Mira",), here=True)))
    _gateway(monkeypatch, '{"readings": [{"family": "attack", "target_id": "npc:mira", "confidence": 0.9, "asks": true}]}',
             '{"readings": [{"family": "talk", "target_id": "npc:archon", "confidence": 0.9, "asks": true}]}')
    named = intent.read_with_model({}, crowd, "what if I punched Mira?").reading
    assert named is not None and (named.family, named.target_id) == ("talk", "npc:mira")
    assert intent.read_with_model({}, crowd, "who is the Archon?").reading is None  # whom to ask is not guessed
    talking = SceneView(crowd.entities, focus_id="npc:mira")
    _gateway(monkeypatch, '{"readings": [{"family": "talk", "target_id": "npc:archon", "confidence": 0.9, "asks": true}]}')
    assert intent.read_with_model({}, talking, "who is the Archon?").reading.target_id == "npc:mira"


def test_a_reading_of_a_family_aimed_at_nothing_keeps_its_family_without_its_target() -> None:
    quest = SceneView((*SCENE.entities, SceneEntity("quest:mill", "quest", ("The Mill",))))
    kept = valid_readings([{"family": "status", "target_id": "quest:mill", "confidence": 0.7,
                            "slots": {"status": ["quests"]}}], quest)
    assert [(reading.family, reading.target_id, reading.slots.status) for reading in kept] == [
        ("status", None, ("quests",))]


def test_an_unclear_line_is_asked_about_with_the_models_question(monkeypatch) -> None:
    from app.apps.rpg.session.turn import intent

    _gateway(monkeypatch, '{"readings": [], "question": "Who are you speaking to?"}',
             '{"readings": [{"family": "talk", "target_id": "npc:bran", "confidence": 0.9}], "question": "Who?"}')
    assert intent.read_with_model({}, SCENE, "tell them").question == "Who are you speaking to?"
    read = intent.read_with_model({}, SCENE, "tell Bran")
    assert read.reading is not None and not read.question  # a reading wins over a question


def test_each_slot_is_kept_only_when_the_scene_and_the_rules_can_take_it() -> None:
    """EV-9: an order the companion rules do not know, a topic the person may not be asked of, a step that is not
    theirs, a quantity past its bounds and a status topic the rules do not tell are dropped, never guessed."""
    scene = SceneView((SceneEntity("npc:bran", "person", ("Bran",), here=True,
                                   topics=(("fact:road", "the road"), ("work", "work")),
                                   steps=(("quest:rumor|ask|0", "Ask Bran"),)),
                       SceneEntity("loc:mill", "place", ("Old Mill",), here=True),
                       SceneEntity("item:rope", "item", ("Rope",), here=True)))
    [talk] = valid_readings([{"family": "talk", "target_id": "npc:bran", "confidence": 0.9, "slots": {
        "topics": ["fact:road", "fact:secret", "loc:mill"], "step": "quest:other|x|0", "status": ["health", "mood"]}}],
        scene)
    assert talk.slots.topics == ("fact:road", "loc:mill") and talk.slots.step == "" and talk.slots.status == ("health",)
    [step] = valid_readings([{"family": "talk", "target_id": "npc:bran", "confidence": 0.9,
                              "slots": {"step": "quest:rumor|ask|0"}}], scene)
    assert step.slots.step == "quest:rumor|ask|0"
    [order] = valid_readings([{"family": "order", "target_id": "npc:bran", "confidence": 0.9,
                               "slots": {"order": "dance", "quantity": 500}}], scene)
    assert order.slots.order == "" and order.slots.quantity is None
    [gift] = valid_readings([{"family": "give", "target_id": "item:rope", "second_target_id": "npc:bran",
                              "confidence": 0.9, "slots": {"quantity": 2}}], scene)
    assert (gift.second_target_id, gift.slots.quantity) == ("npc:bran", 2)
    [choice] = valid_readings([{"family": "grow", "confidence": 0.9, "slots": {"choice": "attribute:luck"}}], scene,
                              choices=["attribute:strength"])
    assert choice.slots.choice == ""


def test_with_no_model_only_the_cards_run(monkeypatch) -> None:
    from app.apps.rpg.foundation import llm_app_gateway
    from app.apps.rpg.session.turn import intent

    monkeypatch.setattr(llm_app_gateway, "build_app_llm_gateway", lambda: None)
    assert intent.read_with_model({}, SCENE, "go to the mill").unavailable


def test_a_line_asks_when_its_best_reading_does() -> None:
    """Review: a lower reading that did not say it asks was still done."""
    import pytest

    from app.apps.rpg.session.turn import intent

    monkeypatch = pytest.MonkeyPatch()
    try:
        _gateway(monkeypatch, '{"readings": [{"family": "attack", "target_id": "npc:bran", "confidence": 0.7, "asks": true},'
                              ' {"family": "attack", "target_id": "npc:bran", "confidence": 0.55}]}')
        read = intent.read_with_model({}, SCENE, "what if I hit Bran?").reading
        assert read is not None and read.family == "talk"  # put to Bran, not done
    finally:
        monkeypatch.undo()


def test_no_creature_that_is_not_here_is_looked_at() -> None:
    """N1 (2026-10-31): a look at someone away failed the turn (their lore is not the scene's). A person away is told
    where they are (``resolution._not_here``); a creature not here is no reading; asked about, either is a question."""
    scene = SceneView((SceneEntity("npc:bran", "person", ("Bran",), here=True),
                       SceneEntity("creature:wolf", "creature", ("wolf",), here=False)))
    assert valid_readings([{"family": "look", "target_id": "creature:wolf", "confidence": 0.9}], scene) == []
    kept = valid_readings([{"family": "look", "target_id": "creature:wolf", "confidence": 0.9, "asks": True},
                           {"family": "look", "target_id": "npc:bran", "confidence": 0.8}], scene)
    assert [(reading.target_id, reading.asks) for reading in kept] == [("creature:wolf", True), ("npc:bran", False)]
