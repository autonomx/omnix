"""The play screen's party follows the simulation's (the playtest: Liora joined, and the party panel stayed empty)."""
from __future__ import annotations

from app.apps.rpg.foundation.state.changes import CompanionHpChanged, CompanionJoined, CompanionLeft
from app.apps.rpg.foundation.state.reducer import reduce


def _document() -> dict:
    return {"manifest": {}, "state": {"party": []}, "simulation_state": {"player_state": {"party_state": {}}}}


def test_the_sheets_party_follows_who_joins_is_hurt_and_leaves() -> None:
    joined, _ = reduce(_document(), [CompanionJoined(npc_id="npc:liora-fen", name="Liora Fen", role="guide")])
    assert [(row["name"], row["role"]) for row in joined["state"]["party"]] == [("Liora Fen", "guide")]
    hurt, _ = reduce(joined, [CompanionHpChanged(npc_id="npc:liora-fen", hp=40)])
    assert hurt["state"]["party"][0]["hp"] == 40
    left, _ = reduce(hurt, [CompanionLeft(npc_id="npc:liora-fen")])
    assert left["state"]["party"] == []


def test_a_new_heros_skills_are_those_of_their_worlds_kind() -> None:
    """The playtest: a hero of Aurelia (fantasy) had firearms and hacking."""
    from app.apps.rpg.session.upgrades.hero_record import hydrate_hero

    fantasy = hydrate_hero({"setup_payload": {"genre": "fantasy_isekai"}, "state": {"player": {}},
                            "simulation_state": {"player_state": {}}})["simulation_state"]["player_state"]["skills"]
    assert "magic" in fantasy and not {"firearms", "hacking"} & set(fantasy)
    future = hydrate_hero({"setup_payload": {"genre": "cyberpunk"}, "state": {"player": {}},
                           "simulation_state": {"player_state": {}}})["simulation_state"]["player_state"]["skills"]
    assert "hacking" in future and not {"magic", "archery"} & set(future)
