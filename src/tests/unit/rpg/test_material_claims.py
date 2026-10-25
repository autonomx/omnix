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
