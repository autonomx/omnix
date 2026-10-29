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


def test_a_title_names_a_calling_and_a_group_is_asked_about() -> None:
    from app.apps.rpg.session.command_reading import scene_view

    simulation = {"world_model": {"npcs": {"npc:kade": {"name": "Dr. Selene Kade", "role": "clinical director"},
                                           "npc:juno": {"name": "Juno Rask", "role": "crane operator"}},
                                  "groups": {"ent:groups:union": {"name": "Red Knives Union", "summary": "Dockers."}}},
                  "present_npc_state": {"present_npc_ids": ["npc:kade", "npc:juno"]}}
    scene = scene_view(simulation)
    assert parse_command("ask the doctor about the docks", scene).target_id == "npc:kade"
    union = parse_command("what is the union?", scene)
    assert (union.family, union.target_id) == ("ask", "ent:groups:union")


def test_a_thing_of_the_heros_by_its_kind_is_never_a_verb_or_anothers() -> None:
    """The review: "drink some water" drank a Healing Potion, and "drop your weapon!" dropped the hero's dagger."""
    scene = SceneView((
        SceneEntity("npc:orik", "person", ("Orik Stonewake", "Orik"), here=True),
        SceneEntity("item:potion", "item", ("Healing Potion", "my potion"), here=True),
        SceneEntity("item:dagger", "item", ("Iron Dagger", "my dagger", "my knife", "my weapon"), here=True),
    ))
    assert parse_command("drop my weapon", scene).target_id == "item:dagger"
    for text in ("Orik, drop your weapon", "put down your weapon!"):
        assert parse_command(text, scene).target_id != "item:dagger", text
    assert parse_command("use my knife to cut the rope", scene).target_id == "item:dagger"


def test_a_question_goes_to_the_seller_of_what_is_asked_and_to_whom_the_hero_talks_with() -> None:
    """The review: "how much is a potion?" went to whoever was here first, and a question put to Brindle about the
    captain went to the captain."""
    scene = SceneView((
        SceneEntity("npc:orik", "person", ("Orik Stonewake", "Orik"), here=True),
        SceneEntity("npc:brindle", "person", ("Brindle Gearwing", "Brindle"), here=True),
        SceneEntity("npc:rhea", "person", ("Captain Rhea Sunward", "the captain"), here=True),
        SceneEntity("item:healing-potion", "item", ("Healing Potion", "potion")),
        SceneEntity("npc:brindle:healing-potion", "offer", ("Healing Potion",), here=True),
    ))
    priced = parse_command("how much is a potion?", scene)
    assert (priced.reason, priced.second_target_id) == ("asks_about_thing", "npc:brindle")
    talking = SceneView(scene.entities, focus_id="npc:brindle")
    asked = parse_command("what do you think of the captain?", talking)
    assert (asked.target_id, asked.second_target_id) == ("npc:rhea", "npc:brindle")
    assert parse_command("what do you think of the captain?", scene).target_id == "npc:rhea"  # no one in focus: hers


def test_a_name_at_the_end_is_whom_a_question_is_put_to_and_a_word_is_no_near_thing() -> None:
    """The tenth review: talking with Brindle, "what do you sell, Orik?" went to Brindle; "is the dagger sharp?"
    asked about the Aether Shard on sale; "drop your dagger!" dropped the hero's."""
    scene = SceneView((
        SceneEntity("npc:orik", "person", ("Orik Stonewake", "Orik"), here=True),
        SceneEntity("npc:brindle", "person", ("Brindle Gearwing", "Brindle"), here=True),
        SceneEntity("item:dagger", "item", ("Iron Dagger", "my dagger"), here=True),
        SceneEntity("npc:brindle:shard", "offer", ("Aether Shard",), here=True),
    ), focus_id="npc:brindle")
    asked = parse_command("what do you sell, Orik?", scene)
    assert (asked.family, asked.target_id) == ("ask", "npc:orik")
    assert parse_command("is the dagger sharp?", scene).target_id == "item:dagger"
    for text in ("drop your dagger!", "Orik, drop your dagger"):
        assert parse_command(text, scene).target_id != "item:dagger", text


def test_the_real_scene_names_offers_by_service_places_by_kind_and_a_groups_leader() -> None:
    """The intent gate's target misses at 9818f0e5e9, by class: offers whose labels have no "supper" or "room", "the
    club" for a nightclub, "the union leader" for the union's elected coordinator, "Master Stonewake" taken for the
    foundry master, and a place and a quest sharing a name."""
    from app.apps.rpg.session.command_reading import scene_view

    simulation = {
        "player_state": {"location_id": "loc:inn"},
        "present_npc_state": {"present_npc_ids": ["npc:orik", "npc:juno"]},
        "world_model": {
            "npcs": {"npc:orik": {"name": "Orik Stonewake", "role": "innkeeper", "location_id": "loc:inn"},
                     "npc:hollis": {"name": "Hollis Brask", "role": "foundry master and armourer"},
                     "npc:juno": {"name": "Juno Rask", "role": "crane operator and elected Red Knives strike coordinator"}},
            "groups": {"g:union": {"name": "Red Knives Union", "summary": "A dock union."}},
            "providers": {"npc:orik": {"location_id": "loc:inn"}},
            "offers": {"npc:orik": [
                {"offer_id": "npc:orik:night", "service_kind": "lodging", "label": "A night's lodging"},
                {"offer_id": "npc:orik:meal", "service_kind": "meal", "label": "A hot meal"}]},
            "locations": {
                "loc:inn": {"name": "The Lantern Below", "description": "A low inn of warm stone."},
                "loc:club": {"name": "The Undertone", "description": "A nightclub and neutral exchange built around a pump."},
                "loc:meridian": {"name": "Hollow Meridian", "description": "A ruin."}},
            "quests": {"quest:meridian": {"title": "The Hollow Meridian"}},
        },
    }
    scene = scene_view(simulation)
    assert parse_command("what's the price of supper?", scene).target_id == "npc:orik:meal"
    assert parse_command("buy a room", scene).target_id == "npc:orik:night"
    assert parse_command("I make my way to the club", scene).target_id == "loc:club"
    assert parse_command("I ask the union leader for advice", scene).target_id == "npc:juno"
    assert parse_command("Master Stonewake, who are you?", scene).target_id == "npc:orik"
    assert parse_command("ask the master about blades", scene).target_id == "npc:hollis"
    assert parse_command("where is the Hollow Meridian?", scene).target_id == "loc:meridian"


def test_someone_not_here_is_no_one_to_look_at_closely() -> None:
    """The narration gate: "examine Dr. Kade" from the docks, planned as a close look, asked the scene's lore for
    someone not in it, and the turn failed."""
    scene = SceneView((
        SceneEntity("npc:juno", "person", ("Juno Rask", "Juno"), here=True),
        SceneEntity("npc:kade", "person", ("Dr. Selene Kade", "Kade")),
        SceneEntity("loc:clinic", "place", ("Halcyon Memory Clinic", "the clinic")),
    ))
    away = parse_command("examine Dr. Selene Kade", scene)
    assert away.confidence < 0.7 and away.reason == "inspects_someone_away"  # the model reads what is meant
    looks = parse_command("what does Dr. Selene Kade look like?", scene)
    assert looks.family == "ask"  # a question about her, for whoever is here
    assert parse_command("examine Juno", scene).family == "inspect"
    assert parse_command("look at the clinic", scene).family == "inspect"


def test_a_question_put_to_someone_by_name_first_is_theirs_to_answer() -> None:
    """The narration gate: talking with Bran, "Mira, can you tell me about the road north?" was answered by Bran (the
    words after the name kept the answerer a question to no one would have)."""
    scene = SceneView((
        SceneEntity("npc:bran", "person", ("Bran", "the barkeep"), here=True),
        SceneEntity("npc:mira", "person", ("Mira",), here=True),
        SceneEntity("loc:road", "place", ("the road north",)),
    ), focus_id="npc:bran")
    for text in ("Mira, can you tell me about the road north?", "Mira, have you heard of the road north?"):
        asked = parse_command(text, scene)
        assert (asked.target_id, asked.second_target_id, asked.reason) == ("npc:mira", None, "asks_someone"), text
