"""The world's people through the day (rules/routines.py, RQ-2.7)."""
from __future__ import annotations

from app.apps.rpg.rules import routines

INN, SQUARE, ROAD = "location:inn", "location:square", "location:road"


def _simulation(*, hero_at: str = INN, scene: tuple[str, ...] = (), party: tuple[str, ...] = (),
                index: dict | None = None) -> dict:
    return {
        "world_model": {
            "locations": {INN: {"name": "The Inn"}, SQUARE: {"name": "The Square"}, ROAD: {"name": "The Road"}},
            "npcs": {"npc:ada": {"name": "Ada", "location_id": INN}, "npc:bo": {"name": "Bo", "location_id": SQUARE},
                     "npc:cy": {"name": "Cy", "location_id": ROAD}},
            "routines": [
                {"npc_id": "npc:ada", "schedule": [
                    {"from_hour": 22, "to_hour": 6, "location_id": INN, "activity": "asleep"},
                    {"from_hour": 6, "to_hour": 22, "location_id": SQUARE, "activity": "selling"}]},
                {"npc_id": "npc:bo", "schedule": [
                    {"from_hour": 0, "to_hour": 24, "location_id": "location:nowhere", "activity": "lost"}]},
            ],
        },
        "npc_index": index or {},
        "player_state": {"location_id": hero_at, "party_state": {"companions": [{"npc_id": npc} for npc in party]}},
        "present_npc_state": {"location_id": hero_at, "present_npc_ids": list(scene)},
    }


def _at(hour: float, day: int = 0) -> int:
    return int(day * routines.MINUTES_PER_DAY + hour * 60)


def test_away_from_the_hero_a_person_is_where_their_day_puts_them() -> None:
    simulation = _simulation(hero_at=ROAD)
    assert routines.whereabouts(simulation, _at(7))["npc:ada"] == routines.Whereabouts(SQUARE, "selling")
    assert routines.whereabouts(simulation, _at(23))["npc:ada"] == routines.Whereabouts(INN, "asleep")
    assert routines.whereabouts(simulation, _at(3, day=2))["npc:ada"].location_id == INN  # past midnight wraps


def test_someone_in_the_scene_stays_until_their_day_turns() -> None:
    simulation = _simulation(hero_at=INN, scene=("npc:ada",))
    assert routines.whereabouts(simulation, _at(5), since=_at(4))["npc:ada"] == routines.Whereabouts(INN, "asleep")
    assert routines.whereabouts(simulation, _at(7), since=_at(8))["npc:ada"].location_id == INN  # not the day's turn
    assert routines.whereabouts(simulation, _at(6.5), since=_at(5.5))["npc:ada"].location_id == SQUARE
    assert routines.whereabouts(simulation, _at(7, day=1), since=_at(7))["npc:ada"].location_id == SQUARE  # a day
    assert routines.present_at(simulation, INN, _at(6.5), since=_at(5.5)) == []


def test_without_a_routine_people_stay_where_they_are_and_companions_follow_the_hero() -> None:
    simulation = _simulation(hero_at=ROAD, party=("npc:ada",), index={"npc:cy": {"location_id": SQUARE}})
    found = routines.whereabouts(simulation, _at(12))
    assert found["npc:ada"].location_id == ROAD  # with the hero, whatever the day says
    assert found["npc:bo"].location_id == SQUARE  # a step to a place the world lacks is not followed
    assert found["npc:cy"].location_id == SQUARE  # where the index last saw them
    assert routines.present_at(simulation, SQUARE, _at(12)) == ["npc:bo", "npc:cy", "npc:ada"]  # the party comes


def test_the_hero_sees_who_comes_and_goes() -> None:
    world = _simulation()["world_model"]
    lines = routines.comings_and_goings(world, ["npc:ada", "npc:bo"], ["npc:bo", "npc:cy"], {
        "npc:ada": routines.Whereabouts(SQUARE, "selling"), "npc:cy": routines.Whereabouts(INN, "drinking")})
    assert lines == ["Ada leaves for The Square.", "Cy arrives, drinking."]
    assert routines.described(_simulation(hero_at=SQUARE), ["npc:ada", "npc:bo"], _at(9)) == ["Ada (selling)", "Bo"]
