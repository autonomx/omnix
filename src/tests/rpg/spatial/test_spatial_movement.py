from app.apps.rpg.spatial.graph import get_entity_area
from app.apps.rpg.spatial.movement import can_move_between, move_entity
from tests.rpg.spatial.fixtures import (
    tavern_spatial_fixture,
    tavern_spatial_fixture_with_private_door_open,
)


def test_open_door_allows_movement():
    graph = tavern_spatial_fixture()
    result = can_move_between(graph, "tavern_common_room", "street")

    assert result["ok"] is True
    assert result["reason"] == "passable"


def test_closed_door_blocks_movement():
    graph = tavern_spatial_fixture()
    result = can_move_between(graph, "tavern_common_room", "private_room")

    assert result["ok"] is False
    assert result["reason"] == "closed"


def test_opened_private_door_allows_movement():
    graph = tavern_spatial_fixture_with_private_door_open()
    result = can_move_between(graph, "tavern_common_room", "private_room")

    assert result["ok"] is True
    assert result["reason"] == "passable"


def test_locked_door_blocks_movement():
    graph = tavern_spatial_fixture()
    result = can_move_between(graph, "tavern_common_room", "cellar")

    assert result["ok"] is False
    assert result["reason"] == "locked"


def test_wall_blocks_movement():
    graph = tavern_spatial_fixture()
    result = can_move_between(graph, "tavern_common_room", "sealed_room")

    assert result["ok"] is False
    assert result["reason"] == "blocked"


def test_move_entity_does_not_update_area_on_failure():
    graph = tavern_spatial_fixture()
    result = move_entity(graph, "player", "cellar")

    assert result["ok"] is False
    assert result["moved"] is False
    assert get_entity_area(graph, "player") == "tavern_common_room"
