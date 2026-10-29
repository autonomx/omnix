"""The narrator says only what the rules did (RQ-3.3): amounts, levels and things gained must be in the evidence."""
from __future__ import annotations

from app.apps.rpg.narration.narrative_engine.validation import _unsupported_material

EVIDENCE = "quest complete: first night in aurelia. you receive 20 silver, wayfarer sigil. you gain 40 experience."


def test_what_the_outcome_holds_may_be_said() -> None:
    assert _unsupported_material("You receive 20 silver and the Wayfarer Sigil, and gain 40 experience.", EVIDENCE) == []
    assert _unsupported_material("You receive a warm welcome and gain the attention of the room.", EVIDENCE) == []


def test_what_the_rules_did_not_do_is_caught() -> None:
    assert _unsupported_material("You receive 1000 gold and a Crown of Kings.", EVIDENCE) == ["1000 gold", "Crown of Kings"]
    assert _unsupported_material("You reach level 9.", EVIDENCE) == ["level 9"]
    assert _unsupported_material("You lose 30 health.", EVIDENCE) == ["30 health"]


def test_a_fights_health_may_be_said_as_its_lines_give_it() -> None:
    fight = "the echo wolf hits you for 2 (98 of 100 left)."
    assert _unsupported_material("The bite leaves you at 98 of 100 health.", fight) == []
    assert _unsupported_material("You lose 2 health and have 98 health left.", fight) == []
    assert _unsupported_material("You are down to 50 health.", fight) == ["50 health"]


def test_only_the_line_that_hits_the_hero_says_the_heros_health() -> None:
    fight = "you hit the wolf for 4 (6 of 10 left). the wolf hits you for 2 (98 of 100 left)."
    assert _unsupported_material("You have 98 of 100 health.", fight) == []
    assert _unsupported_material("You have 6 health.", fight) == ["6 health"]  # the wolf's
    assert _unsupported_material("You lose 4 health.", fight) == ["4 health"]  # the wolf's wound
    assert _unsupported_material("You are at 10 hp.", fight) == ["10 hp"]  # the wolf's most


def test_a_foes_health_may_be_said_as_its_blows_give_it() -> None:
    """The playtest: "the wolf, down to 4 of its 10 health" sent the writer back to write the turn again."""
    fight = "you hit the wolf for 4 (6 of 10 left). the wolf hits you for 2 (98 of 100 left)."
    assert _unsupported_material("The wolf is down to 6 of its 10 health.", fight) == []
    assert _unsupported_material("The blow takes 4 health from the wolf.", fight) == []  # "your" would mark the hero
    assert _unsupported_material("The wolf has 50 health.", fight) == ["50 health"]  # no blow says it


def test_a_foes_numbers_never_stand_for_the_heros_health() -> None:
    """The review: "the bite drops you to 5 health" passed on the wolf's "5 of 8 left"."""
    fight = "the wolf hits you for 4 (6 of 10 left). you hit the wolf for 3 (5 of 8 left)."
    for said in ("The bite drops you to 5 health.", "Bleeding, down to 5 health, you press on.",
                 "With 5 health left you grit your teeth.", "Your health falls to 5 health."):
        assert _unsupported_material(said, fight) == ["5 health"], said
    assert _unsupported_material("The wolf is down to 6 health.", fight) == ["6 health"]  # the hero's, not the wolf's
    assert _unsupported_material("The wolf staggers, down to 5 of its 8 health.", fight) == []


def test_a_clause_that_points_at_the_foe_may_give_its_health() -> None:
    """The second review: "you hit the wolf, leaving it at 5 health" sent the writer back again."""
    fight = "the wolf hits you for 4 (6 of 10 left). you hit the wolf for 3 (5 of 8 left)."
    for said in ("You hit the wolf, leaving it at 5 health.", "You drive the wolf back; it has 5 health left.",
                 "You strike true; the wolf staggers, down to 5 of its 8 health."):
        assert _unsupported_material(said, fight) == [], said
    assert _unsupported_material("Bleeding, down to 5 health, you press on.", fight) == ["5 health"]


def test_your_arm_is_the_heros() -> None:
    fight = "the wolf hits you for 4 (6 of 10 left). you hit the wolf for 3 (5 of 8 left)."
    assert _unsupported_material("Your arm bleeds, 5 health left.", fight) == ["5 health"]
    assert _unsupported_material("Its jaws close on your arm, leaving 5 health.", fight) == ["5 health"]
    assert _unsupported_material("Your strike leaves the wolf at 5 of its 8 health.", fight) == []


def test_a_clause_naming_the_foe_the_turn_hit_may_give_its_health() -> None:
    """The review: "your" elsewhere in the sentence made the wolf's own health the hero's claim."""
    fight = "you hit the echo wolf for 4 (5 of 10 left)."
    for said in ("Your blade bites deep, and the wolf staggers at 5 health.", "Your strike lands; the wolf is down to 5 health."):
        assert _unsupported_material(said, fight) == [], said
    assert _unsupported_material("Your blade bites deep, and the crowd sees you at 5 health.", fight) == ["5 health"]


def test_only_a_foe_the_turns_blows_struck_may_own_a_health_figure() -> None:
    """The tenth review: any "the X" the scene named let a claim of the hero's health pass."""
    evidence = "the echo wolf hits you for 3 (17 of 20 left). starfall village at night."
    for said in ("Your knees buckle, the night closing in at 5 health.",
                 "Your vision swims, the echo of the blow leaving 10 health."):
        assert _unsupported_material(said, evidence), said


def test_a_foe_named_whole_may_own_its_health() -> None:
    """The eleventh review: only the struck name's last word counted, so "the echo wolf staggers" failed."""
    fight = "you hit the echo wolf for 4 (5 of 10 left)."
    assert _unsupported_material("You slash, and the echo wolf staggers at 5 health.", fight) == []
    assert _unsupported_material("You strike; the rust-golem 7 sags at 5 health.",
                                 "you hit the rust-golem 7 for 4 (5 of 10 left).") == []


def test_a_word_a_foes_name_shares_with_the_scene_owns_no_health() -> None:
    """The twelfth review: "the sky" or "the echo" of a struck Sky Manta or Echo Wolf let the hero's health claim pass."""
    fight = "you hit the sky manta for 4 (5 of 10 left). you hit the echo wolf for 2 (9 of 10 left)."
    assert _unsupported_material("Your head rings, the sky spinning at 9 health.", fight) == ["9 health"]
    assert _unsupported_material("Your vision swims, the echo of the blow leaving 5 health.", fight) == ["5 health"]
    assert _unsupported_material("Your blade bites, and the manta reels at 5 health.", fight) == []


def test_a_person_struck_is_owned_by_any_word_of_their_name() -> None:
    """The thirteenth review: people are struck by name, bare, so "the captain" is the captain's."""
    fight = "you hit captain rhea sunward for 4 (6 of 10 left)."
    assert _unsupported_material("Your blow lands, and the captain staggers back at 6 health.", fight) == []


def test_your_body_is_the_heros() -> None:
    """The fourteenth review: "the captain's blade leaving 6 health in your body" is the hero's health."""
    fight = "you hit captain rhea sunward for 4 (6 of 10 left). captain rhea sunward hits you for 3 (17 of 20 left)."
    assert _unsupported_material("You reel, the captain's blade leaving 6 health in your body.", fight) == ["6 health"]
