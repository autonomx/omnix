import json

from app.rpg.spatial.serialization import normalize_spatial_graph
from tests.rpg.spatial.fixtures import tavern_spatial_fixture


def test_spatial_graph_json_roundtrip_stable():
    graph = normalize_spatial_graph(tavern_spatial_fixture())

    encoded = json.dumps(graph, sort_keys=True)
    decoded = json.loads(encoded)
    normalized = normalize_spatial_graph(decoded)

    assert normalized == graph
    assert normalized["current_area_id"] == "tavern_common_room"