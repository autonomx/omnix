"""The command grammar reads whole words against the scene (RQ-3.1)."""
from __future__ import annotations

import pytest

from app.apps.rpg.rules.intent.grammar import SceneEntity, SceneView, parse_command

SCENE = SceneView((
    SceneEntity("npc:brindle", "person", ("Brindle Gearwing", "the relic merchant", "Brindle"), here=True),
    SceneEntity("npc:liora", "person", ("Liora Fen", "my guide", "Liora"), here=True),
    SceneEntity("npc:archon", "person", ("Archon Malrec", "the Archon")),
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
