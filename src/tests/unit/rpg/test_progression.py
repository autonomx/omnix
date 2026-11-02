"""The hero's progression (rules/player/progression.py; docs/rpg/design/progression.md)."""
from __future__ import annotations

from app.apps.rpg.foundation.state import reduce
from app.apps.rpg.rules.player import progression


def _document(*, level: int = 1, xp: int = 0, pending: int = 0) -> dict:
    return {"manifest": {}, "simulation_state": {"player_state": {
                "level": level, "xp": xp, "level_choices_pending": pending,
                "stats": {"strength": 10, "constitution": 14},
                "resources": {"hp": {"current": 20, "max": 20}},
                "skills": {"stealth": {"level": 4, "xp": 240}, "archery": {"level": 0, "xp": 0}}}},
            "state": {"player": {"stats": {"strength": 10}},
                      "ability_tree": {"abilities": [{"ability_id": "a:volley", "name": "Volley", "level_required": 2},
                                                     {"ability_id": "a:storm", "name": "Arrow Storm", "level_required": 9}]},
                      "ability_state": {"unlocked": []}}}


def test_one_curve_levels_the_hero_and_each_level_brings_health_and_a_choice() -> None:
    assert [progression.xp_to_next(level) for level in (1, 2, 3, 4)] == [100, 200, 300, 400]  # 100, 300, 600, 1,000
    document = _document(xp=90)
    changes, lines = progression.gain(document["simulation_state"], 320)
    reached = changes[-1]
    assert (reached.level, reached.xp, reached.choices_pending, reached.max_hp_gain) == (3, 110, 2, 14)  # con +2
    assert lines[-1] == progression.GROWTH_CHOICES
    after, _ = reduce(document, changes)
    assert after["simulation_state"]["player_state"]["resources"]["hp"] == {"current": 34, "max": 34}


def test_a_levels_choice_raises_an_attribute_teaches_an_ability_or_two_skills() -> None:
    document = _document(level=2, pending=2)
    raised = progression.choose(document, "attribute:strength")
    document, _ = reduce(document, raised.changes)
    assert document["simulation_state"]["player_state"]["stats"]["strength"] == 12
    assert document["state"]["player"]["stats"]["strength"] == 12
    learned = progression.choose(document, "ability:a:volley")
    document, _ = reduce(document, learned.changes)
    assert document["state"]["ability_state"]["unlocked"] == ["a:volley"]
    assert document["simulation_state"]["player_state"]["level_choices_pending"] == 0
    assert progression.choose(document, "skills:stealth,archery").refused  # no choice waits now
    assert progression.choose(_document(level=2, pending=1), "ability:a:storm").refused  # level 9's


def test_skills_rise_to_rank_five_on_their_own_curve() -> None:
    simulation = _document()["simulation_state"]
    assert [progression.skill_xp_to_next(rank) for rank in (0, 1, 4)] == [50, 100, 250]
    changes, lines = progression.skill_gain(simulation, "stealth", 20)
    assert (changes[0].level, changes[0].xp) == (5, 0) and lines[-1] == "Stealth rises to rank 5."
    capped = {**simulation, "player_state": {**simulation["player_state"], "skills": {"stealth": {"level": 5}}}}
    assert progression.skill_gain(capped, "stealth", 20) == ([], [])
