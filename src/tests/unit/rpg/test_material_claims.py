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
