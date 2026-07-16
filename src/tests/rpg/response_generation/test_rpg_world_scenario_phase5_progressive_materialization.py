from __future__ import annotations

import pytest

from app.rpg.worlds.progressive_materialization import (
    _affected_slots,
    _updated_plan,
)
from app.rpg.worlds.starter_bubble import (
    build_starter_bubble,
    build_starter_map_definitions,
    predictive_materialization_queue,
)


def test_deferred_slot_and_adjacent_map_gain_bidirectional_portals() -> None:
    plan = build_starter_bubble(
        world_id="world:progressive",
        source_world_revision=2,
        starting_location_id="location:harbor",
        neighboring_location_id="location:old-road",
    )
    frontier_id = "location:old-road:frontier"
    neighbor_id = "location:old-road"

    promoted = _updated_plan(plan, frontier_id)
    affected = _affected_slots(promoted, frontier_id)
    definitions = build_starter_map_definitions(
        promoted,
        target_world_revision=3,
        definition_revisions={
            str(slot.map_id): 2 for slot in affected if slot.map_id
        },
    )
    affected_map_ids = {slot.map_id for slot in affected}
    affected_definitions = tuple(
        definition
        for definition in definitions
        if definition.map_id in affected_map_ids
    )
    frontier = promoted.slot(frontier_id)
    neighbor = promoted.slot(neighbor_id)
    frontier_definition = next(
        definition
        for definition in affected_definitions
        if definition.map_id == frontier.map_id
    )
    neighbor_definition = next(
        definition
        for definition in affected_definitions
        if definition.map_id == neighbor.map_id
    )

    assert frontier.deferred is False
    assert frontier.simulation_readiness == "navigable"
    assert frontier.presentation_readiness == "assets_pending"
    assert {slot.location_id for slot in affected} == {frontier_id, neighbor_id}
    assert frontier_definition.definition_revision == 2
    assert neighbor_definition.definition_revision == 2
    assert frontier_definition.is_walkable((4, 4)) is True
    assert frontier_definition.metadata["presentation_fallback"] == (
        "semantic_grid_placeholder"
    )
    assert frontier_definition.metadata["art_optional"] is True
    assert {portal.target.map_id for portal in frontier_definition.portals} == {
        neighbor.map_id
    }
    assert frontier.map_id in {
        portal.target.map_id for portal in neighbor_definition.portals
    }
    assert predictive_materialization_queue(
        promoted,
        current_location_id=frontier_id,
    ) == ()


def test_materialization_rejects_non_deferred_slots() -> None:
    plan = build_starter_bubble(
        world_id="world:progressive",
        source_world_revision=2,
        starting_location_id="location:harbor",
    )

    with pytest.raises(ValueError, match="location_not_deferred"):
        _updated_plan(plan, "location:harbor")
