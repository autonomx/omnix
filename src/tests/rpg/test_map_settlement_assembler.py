from __future__ import annotations

from app.rpg.map_serialization import canonical_map_json
from app.rpg.map_settlement_assembler import (
    ASSEMBLER_VERSION,
    assemble_settlement_map,
    validate_settlement_assembly,
)
from app.rpg.world_graph import RpgLocationNode, RpgRegionGraph, RpgRoute


def _graph(*, reverse: bool = False) -> RpgRegionGraph:
    nodes = [
        RpgLocationNode(
            id="frost_haven",
            name="Frost Haven",
            region_id="northern_pass",
            status="expanded",
            services=("inn", "market", "smithy", "healer"),
        ),
        RpgLocationNode(id="old_quarry", name="Old Quarry", region_id="northern_pass", status="expanded"),
        RpgLocationNode(id="frostpine_hollow", name="Frostpine Hollow", region_id="northern_pass", status="expanded"),
        RpgLocationNode(id="glimmerdeep_pass", name="Glimmerdeep Pass", region_id="northern_pass", status="stub"),
    ]
    routes = [
        RpgRoute("frost_haven", "old_quarry", id="route:frost-quarry"),
        RpgRoute("frost_haven", "frostpine_hollow", id="route:frost-hollow"),
        RpgRoute("frost_haven", "glimmerdeep_pass", id="route:frost-glimmer"),
    ]
    if reverse:
        nodes.reverse()
        routes.reverse()
    return RpgRegionGraph(
        locations={node.id: node for node in nodes},
        routes=tuple(routes),
    )


def test_same_seed_and_graph_produce_byte_identical_assembly() -> None:
    first = assemble_settlement_map(424242, _graph(), "frost_haven")
    second = assemble_settlement_map(424242, _graph(reverse=True), "frost_haven")

    assert first.assembler_version == ASSEMBLER_VERSION
    assert first.canonical_bytes() == second.canonical_bytes()
    assert canonical_map_json(first.definition) == canonical_map_json(second.definition)
    assert first.definition.definition_revision == second.definition.definition_revision


def test_different_seed_changes_layout_but_preserves_contract_shape() -> None:
    first = assemble_settlement_map(101, _graph(), "frost_haven")
    second = assemble_settlement_map(202, _graph(), "frost_haven")

    assert first.canonical_bytes() != second.canonical_bytes()
    assert len(first.zones) == len(second.zones) == 4
    assert len(first.parcels) == len(second.parcels) == 16
    assert len(first.definition.objects) == len(second.definition.objects) == 19
    assert len(first.definition.route_geometry) == len(second.definition.route_geometry) == 5


def test_assembled_parcels_and_buildings_are_bounded_and_collision_free() -> None:
    assembly = assemble_settlement_map(7, _graph(), "frost_haven")

    validate_settlement_assembly(assembly)
    assert len({parcel.id for parcel in assembly.parcels}) == len(assembly.parcels)
    assert all(parcel.bounds.width > 0 and parcel.bounds.height > 0 for parcel in assembly.parcels)
    assert all(item.hitbox is not None and item.footprint is not None for item in assembly.definition.objects)
    assert all(assembly.definition.bounds.contains((item.x, item.y)) for item in assembly.definition.objects)


def test_assembler_uses_world_graph_exits_for_stable_gates_and_routes() -> None:
    assembly = assemble_settlement_map(88, _graph(), "frost_haven")
    object_ids = {item.id for item in assembly.definition.objects}
    route_ids = {item.route_id for item in assembly.definition.route_geometry}

    assert {
        "gate:frost_haven:frostpine_hollow",
        "gate:frost_haven:glimmerdeep_pass",
        "gate:frost_haven:old_quarry",
    } <= object_ids
    assert {
        "route:frost_haven:exit:frostpine_hollow",
        "route:frost_haven:exit:glimmerdeep_pass",
        "route:frost_haven:exit:old_quarry",
    } <= route_ids


def test_assembler_fails_for_unknown_settlement_source() -> None:
    try:
        assemble_settlement_map(1, _graph(), "missing")
    except ValueError as error:
        assert str(error) == "settlement_location_missing:missing"
    else:
        raise AssertionError("expected missing source error")
