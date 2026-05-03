from app.rpg.spatial.graph import (
    find_connection,
    list_area_connections,
    list_entities_in_area,
    set_entity_area,
)
from app.rpg.spatial.serialization import normalize_spatial_graph
from tests.rpg.spatial.fixtures import tavern_spatial_fixture


def test_normalize_spatial_graph_roundtrip_basic_shape():
    graph = normalize_spatial_graph(tavern_spatial_fixture())

    assert graph["current_area_id"] == "tavern_common_room"
    assert "tavern_common_room" in graph["areas"]
    assert "common_private_door" in graph["connections"]
    assert graph["entity_locations"]["player"]["area_id"] == "tavern_common_room"


def test_find_connection_supports_bidirectional_connections():
    graph = tavern_spatial_fixture()

    forward = find_connection(graph, "tavern_common_room", "kitchen")
    reverse = find_connection(graph, "kitchen", "tavern_common_room")

    assert forward
    assert reverse
    assert reverse["to_area_id"] == "tavern_common_room"


def test_list_area_connections_includes_reverse_edges():
    graph = tavern_spatial_fixture()
    connections = list_area_connections(graph, "kitchen")

    assert any(c["to_area_id"] == "tavern_common_room" for c in connections)


def test_set_entity_area_updates_player_current_area():
    graph = tavern_spatial_fixture()
    graph = set_entity_area(graph, "player", "street")

    assert graph["entity_locations"]["player"]["area_id"] == "street"
    assert graph["current_area_id"] == "street"


def test_list_entities_in_area_returns_only_area_entities():
    graph = tavern_spatial_fixture()
    entity_ids = {e["entity_id"] for e in list_entities_in_area(graph, "tavern_common_room")}

    assert "player" in entity_ids
    assert "bran" in entity_ids
    assert "mira" not in entity_ids