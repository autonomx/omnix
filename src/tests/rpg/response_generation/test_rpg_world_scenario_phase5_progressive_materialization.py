from __future__ import annotations

import pytest

from app.rpg.worlds.progressive_materialization import _updated_plan
from app.rpg.worlds.starter_bubble import (
    build_starter_bubble,
    build_starter_map_definitions,
    predictive_materialization_queue,
)


def test_deferred_slot_becomes_navigable_without_waiting_for_art() -> None:
    plan = build_starter_bubble(
        world_id="world:progressive",
        source_world_revision=2,
        starting_location_id="location:harbor",
        neighboring_location_id="location:old-road",
    )
    frontier_id = "location:old-road:frontier"

    promoted = _updated_plan(plan, frontier_id)
    definitions = build_starter_map_definitions(
        promoted,
        target_world_revision=3,
    )
    frontier = promoted.slot(frontier_id)
    frontier_definition = next(
        definition for definition in definitions if definition.map_id == frontier.map_id
    )

    assert frontier.deferred is False
    assert frontier.simulation_readiness == "navigable"
    assert frontier.presentation_readiness == "assets_pending"
    assert frontier_definition.is_walkable((4, 4)) is True
    assert frontier_definition.metadata["presentation_fallback"] == "semantic_grid_placeholder"
    assert frontier_definition.metadata["art_optional"] is True
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
