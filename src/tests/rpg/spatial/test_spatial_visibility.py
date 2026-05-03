from app.rpg.spatial.visibility import (
    can_see_area,
    can_see_entity,
    visible_entities_from,
)
from tests.rpg.spatial.fixtures import (
    tavern_spatial_fixture,
    tavern_spatial_fixture_with_private_door_open,
)


def test_same_room_visibility():
    graph = tavern_spatial_fixture()
    result = can_see_entity(graph, "player", "bran")

    assert result["ok"] is True
    assert result["reason"] == "same_area"


def test_hidden_npc_not_visible_even_if_area_visible():
    graph = tavern_spatial_fixture_with_private_door_open()
    result = can_see_entity(graph, "player", "spy")

    assert result["ok"] is False
    assert result["reason"] == "hidden"


def test_closed_door_blocks_visibility():
    graph = tavern_spatial_fixture()
    result = can_see_area(graph, "tavern_common_room", "private_room")

    assert result["ok"] is False
    assert result["reason"] == "blocked_by_barrier"


def test_open_door_allows_visibility():
    graph = tavern_spatial_fixture_with_private_door_open()
    result = can_see_area(graph, "tavern_common_room", "private_room")

    assert result["ok"] is True
    assert result["visibility"] == "open"


def test_wall_blocks_visibility():
    graph = tavern_spatial_fixture()
    result = can_see_area(graph, "tavern_common_room", "sealed_room")

    assert result["ok"] is False
    assert result["visibility"] == "blocked"


def test_visible_entities_only_returns_visible_entities():
    graph = tavern_spatial_fixture()
    visible_ids = {e["entity_id"] for e in visible_entities_from(graph, "player")}

    assert "bran" in visible_ids
    assert "mira" in visible_ids
    assert "bandit" in visible_ids
    assert "spy" not in visible_ids