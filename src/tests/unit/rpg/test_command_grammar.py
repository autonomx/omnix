"""The command grammar reads whole words against the scene (RQ-3.1)."""
from __future__ import annotations

import pytest

from app.apps.rpg.rules.intent.grammar import SceneEntity, SceneView, parse_command

SCENE = SceneView((
    SceneEntity("npc:brindle", "person", ("Brindle Gearwing", "the relic merchant", "Brindle"), here=True),
    SceneEntity("npc:liora", "person", ("Liora Fen", "my guide", "Liora"), here=True),
    SceneEntity("npc:archon", "person", ("Archon Malrec", "the Archon")),
    SceneEntity("npc:rhea", "person", ("Rhea Sunward", "the village guard captain", "the captain")),
    SceneEntity("creature:echo-wolf", "creature", ("echo wolf", "the wolf"), here=True),
    SceneEntity("item:potion", "item", ("healing potion", "potion"), here=True),
    SceneEntity("iron_dagger", "item", ("iron dagger", "dagger", "knife"), here=True),
    SceneEntity("npc:brindle:bread", "offer", ("a loaf of lantern bread", "some lantern bread"), here=True),
    SceneEntity("location:village", "place", ("Starfall Village", "the village"), here=True),
    SceneEntity("location:ruins", "place", ("Moonroot Ruins", "the ruins")),
    SceneEntity("skill:stealth", "skill", ("stealth",), here=True),
    SceneEntity("quest:gate", "quest", ("The Hollow Meridian",), here=True),
))


@pytest.mark.parametrize(("text", "family", "target"), [
    ("look around", "look", None),
    ("lok arround", "look", None),
    ("go to Starfall Village", "move", "location:village"),
    ("goto the village", "move", "location:village"),
    ("buy some lantern bread", "buy", "npc:brindle:bread"),
    ("attack the echo wolf with my dagger", "attack", "creature:echo-wolf"),
    ("I drink the healing potion", "use_item", "item:potion"),
    ("sel my iron dagger", "sell", "iron_dagger"),
    ("I ask Liora Fen where Archon Malrec is", "ask", "npc:liora"),
    ("what do people say about the Archon?", "ask", "npc:archon"),
    ("Liora, where am I?", "ask", "npc:liora"),
    ("Liora, where am I? I woke up here and remember nothing.", "ask", "npc:liora"),  # the playtest's first line
    ("Liora, I woke up here and I remember nothing.", "talk", "npc:liora"),
    ("where am I?", "look", None),
    ("what am I carrying?", "status", None),
    ("tell Liora a joke", "talk", "npc:liora"),
    ("I train my stealth", "practice", "skill:stealth"),
    ("I accept The Hollow Meridian", "quest", "quest:gate"),
    ("ask Liora Fen to join my party", "party", "npc:liora"),
    ("give it to them", "clarify", None),
    ("attack", "clarify", None),
    ("never mind", "decline", None),
    ("rest for a while", "rest", None),
    ("I wait a while", "wait", None),
    ("take a look around", "look", None),
    ("give my iron dagger to Liora Fen", "give", "iron_dagger"),
    ("take off some lantern bread", "unequip", None),  # no order of the bread on sale
    ("I hunt for echo wolves along the pass", "attack", "creature:echo-wolf"),  # the playtest: it came to nothing
    ("search for the wolf", "attack", "creature:echo-wolf"),
    ("search for hidden doors", "manipulate", None),  # a search, as before (no creature named)
])
def test_commands_read_as_their_family_and_target(text, family, target) -> None:
    candidate = parse_command(text, SCENE)
    assert (candidate.family, candidate.target_id) == (family, target)


@pytest.mark.parametrize("text", [
    "That would be useful later.",  # not "use"
    "The forest is quiet.",  # not "rest"
    "What a white sky.",  # not an attack, not a question
    "The current runs fast.",  # not renting
])
def test_words_inside_other_words_do_nothing(text) -> None:
    candidate = parse_command(text, SCENE)
    assert candidate.family == "talk" and not candidate.stateful


def test_a_purchase_of_something_not_on_sale_is_not_stateful() -> None:
    assert parse_command("buy some lantern bread", SCENE).stateful
    assert not parse_command("purchase the Moonroot Ruins", SCENE).stateful


def test_multi_step_commands_keep_their_clauses() -> None:
    candidate = parse_command("I head to the village, then wait", SCENE)
    assert candidate.family == "move" and candidate.clauses == ("i head to the village", "wait")


@pytest.mark.parametrize(("text", "target"), [
    ("what would happen if I attacked Liora Fen?", "npc:liora"),
    ("Liora, what if we stole the potion?", "npc:liora"),
    ("what would Brindle do if I left without paying?", "npc:brindle"),
    ("suppose I attacked the echo wolf", "creature:echo-wolf"),
    ("what would happen if I dropped my dagger?", "iron_dagger"),
])
def test_a_hypothetical_is_asked_never_done(text: str, target: str | None) -> None:
    """RQ-3.2 pilot: "what would happen if I attacked Liora Fen?" started a fight with her."""
    reading = parse_command(text, SCENE)
    assert (reading.family, reading.target_id, reading.reason) == ("ask", target, "asks_hypothetical")
    assert reading.confidence >= 0.8  # the turn plans it as speech, with no intent call to read it as the deed


ABILITY_SCENE = SceneView((*SCENE.entities, SceneEntity("survival_make_camp", "ability", ("Make Camp",), here=True),
                           SceneEntity("aimed_shot", "ability", ("Aimed Shot",), here=True)))


def test_an_ability_is_read_by_its_whole_name_only() -> None:
    assert parse_command("I make my way to the village", ABILITY_SCENE).family == "move"  # "make" is no Make Camp
    assert parse_command("use Aimed Shot on the wolf", ABILITY_SCENE).target_id == "aimed_shot"


@pytest.mark.parametrize(("text", "asked"), [
    ("what does the local news cost?", True), ("Where can I buy bread?", True), ("What could I buy with 5 gold?", True),
    ("What does the bread cost, please?", True), ("should I trust the guide?", True), ("Liora, where am I?", True),
    ("can I buy the bread?", False), ("Liora, can you show me the way?", False), ("Could we buy some bread?", False),
    ("Shall we head to the market?", False), ("Attack the wolf?", False), ("buy the bread", False),
])
def test_a_question_about_a_deed_is_asked_and_a_request_or_command_is_done(text: str, asked: bool) -> None:
    from app.apps.rpg.rules.intent.grammar import asked_not_done

    assert asked_not_done(text) is asked



def test_a_person_is_named_by_the_aliases_their_world_gives_them() -> None:
    """The route's intent eval: "ask the barkeep" did not reach Bran, the innkeeper; a world's people may carry
    aliases (world-author-guide.md)."""
    from app.apps.rpg.session.command_reading import scene_view

    simulation = {"world_model": {"npcs": {"npc:bran": {"name": "Bran", "role": "innkeeper of the Rusty Flagon",
                                                        "aliases": ["the barkeep", "the bartender"]}}},
                  "present_npc_state": {"present_npc_ids": ["npc:bran"]}}
    reading = parse_command("ask the barkeep about the road north", scene_view(simulation))
    assert (reading.family, reading.target_id) == ("ask", "npc:bran")



@pytest.mark.parametrize(("text", "family", "target", "second"), [
    ("Brindle, I'd like some lantern bread.", "buy", "npc:brindle:bread", "npc:brindle"),  # the playtest: a room asked for
    ("Brindle, give me some lantern bread", "buy", "npc:brindle:bread", "npc:brindle"),  # "give me" asks for it
    ("Liora, I give you my dagger", "give", "iron_dagger", "npc:liora"),  # "you" is the one named
    ("Liora, I woke up here and remember nothing.", "talk", "npc:liora", None),
    ("Liora, keep watch", "order", "npc:liora", None),
    ("Liora, join my party", "party", "npc:liora", None),
    # The playtest: "village" named Captain Rhea, the village guard captain, and the invitation went to her.
    ("Liora, will you come with me to the village?", "party", "npc:liora", None),
    # The playtest: asked of the one named, it needs no model to say whom (it was read at 0.6 and sent to the model).
    ("Brindle, tell me about the gate. What do you need from me?", "ask", "npc:brindle", None),
])
def test_a_name_and_a_comma_first_is_said_to_them_or_done_with_them(text, family, target, second) -> None:
    from app.apps.rpg.session.turn.planning import plan_action

    reading = parse_command(text, SCENE)
    assert (reading.family, reading.target_id, reading.second_target_id) == (family, target, second)
    assert plan_action(reading, fighting=False) is not None  # the game's own rules play it, with no model to read it


def test_a_name_first_does_not_take_the_place_of_the_one_the_words_name() -> None:
    """The review: "Liora, dismiss Juno from the party" dismissed Liora."""
    scene = SceneView((*SCENE.entities, SceneEntity("npc:juno", "person", ("Juno Rask", "Juno"), here=True)))
    for text in ("Liora, ask Juno to join the party", "Liora, dismiss Juno from the party"):
        assert parse_command(text, scene).target_id == "npc:juno", text


def test_a_question_aloud_about_someone_here_is_theirs_to_answer() -> None:
    """The narration gate: "should I trust the barkeep?" went to the intent call and became a free action."""
    from app.apps.rpg.session.turn.planning import plan_action

    scene = SceneView((SceneEntity("npc:bran", "person", ("Bran", "the barkeep"), here=True),
                       SceneEntity("npc:aldric", "person", ("Aldric",))))
    for text, target in (("should I trust the barkeep?", "npc:bran"), ("what do people say about Bran?", "npc:bran")):
        reading = parse_command(text, scene)
        planned = plan_action(reading, fighting=False)
        assert (reading.target_id, planned.mechanic, planned.target_id) == (target, "talk", target), text
    # Someone away, asked about aloud: whoever is here answers, about them (the plan tells where they are found).
    away = parse_command("where can I find Aldric?", scene)
    assert (away.target_id, plan_action(away, fighting=False).target_id) == ("npc:aldric", "npc:bran")


def test_a_question_about_a_thing_is_answered_by_its_seller_or_whoever_is_here_and_a_close_look_is_planned() -> None:
    """The intent gate: the grammar read these right, and the intent call, asked again, read some wrong."""
    from app.apps.rpg.session.turn.planning import plan_action

    stew = parse_command("how much is the lantern bread?", SCENE)
    assert (stew.family, stew.target_id, stew.second_target_id) == ("ask", "npc:brindle:bread", "npc:brindle")
    assert plan_action(stew, fighting=False).target_id == "npc:brindle"  # its seller answers
    looked = parse_command("examine the iron dagger", SCENE)
    planned = plan_action(looked, fighting=False)
    assert (planned.mechanic, planned.target_id) == ("look", "iron_dagger")
    no = parse_command("no thanks, Brindle", SCENE)
    assert plan_action(no, fighting=False).mechanic == "talk"


def test_a_thing_carried_and_a_calling_answer_to_their_other_names() -> None:
    """The intent gate: "examine my knife" named no Iron Dagger, "ask the trader" no merchant."""
    from app.apps.rpg.session.command_reading import scene_view

    simulation = {"world_model": {"npcs": {"npc:elara": {"name": "Elara", "role": "merchant of the market square"}}},
                  "present_npc_state": {"present_npc_ids": ["npc:elara"]},
                  "player_state": {"inventory_state": {"items": [{"item_id": "iron_dagger", "name": "Iron Dagger"}]}}}
    scene = scene_view(simulation)
    assert parse_command("examine my knife", scene).target_id == "iron_dagger"
    assert parse_command("ask the trader about the road", scene).target_id == "npc:elara"
    no = parse_command("Elara, no, I don't need anything.", scene)
    assert (no.family, no.target_id) == ("decline", "npc:elara")
