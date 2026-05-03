from app.rpg.spatial.audibility import (
    audible_entities_from,
    can_hear_area,
    can_hear_entity,
)
from tests.rpg.spatial.fixtures import tavern_spatial_fixture


def test_same_room_audibility():
    graph = tavern_spatial_fixture()
    result = can_hear_entity(graph, "player", "bran")

    assert result["ok"] is True
    assert result["reason"] == "same_area"


def test_closed_door_muffles_audibility():
    graph = tavern_spatial_fixture()
    result = can_hear_area(graph, "tavern_common_room", "private_room")

    assert result["ok"] is True
    assert result["audibility"] == "muffled"
    assert result["reason"] == "muffled_by_barrier"


def test_wall_blocks_audibility():
    graph = tavern_spatial_fixture()
    result = can_hear_area(graph, "tavern_common_room", "sealed_room")

    assert result["ok"] is False
    assert result["audibility"] == "blocked"


def test_silent_entity_not_audible_unless_loud():
    graph = tavern_spatial_fixture()

    quiet = can_hear_entity(graph, "player", "silent_rat")
    loud = can_hear_entity(graph, "player", "silent_rat", sound_level="loud")

    assert quiet["ok"] is False
    assert quiet["reason"] == "silent"
    assert loud["ok"] is True


def test_audible_entities_include_muffled_adjacent_entities():
    graph = tavern_spatial_fixture()
    audible_ids = {e["entity_id"] for e in audible_entities_from(graph, "player")}

    assert "bran" in audible_ids
    assert "mira" in audible_ids
    assert "spy" in audible_ids