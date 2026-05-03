from app.rpg.spatial.graph import get_entity_area
from app.rpg.spatial.movement import can_move_between, move_entity
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


def test_move_entity_updates_current_area_on_success():
    graph = tavern_spatial_fixture()
    result = move_entity(graph, "player", "street")

    assert result["ok"] is True
    assert result["moved"] is True
    assert get_entity_area(graph, "player") == "street"
    assert graph["current_area_id"] == "street"


def test_move_entity_does_not_update_area_on_failure():
    graph = tavern_spatial_fixture()
    result = move_entity(graph, "player", "cellar")

    assert result["ok"] is False
    assert result["moved"] is False
    assert get_entity_area(graph, "player") == "tavern_common_room"