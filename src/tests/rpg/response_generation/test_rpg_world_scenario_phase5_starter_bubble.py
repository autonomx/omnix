from __future__ import annotations

from app.rpg.worlds.starter_bubble import (
    build_starter_bubble,
    build_starter_map_definitions,
    predictive_materialization_queue,
    starter_bubble_certification,
)


def test_starter_bubble_separates_simulation_and_presentation_readiness() -> None:
    plan = build_starter_bubble(
        world_id="world:starter",
        source_world_revision=1,
        starting_location_id="location:harbor",
        neighboring_location_id="location:old-road",
    )

    roles = {slot.role for slot in plan.slots}
    assert roles == {"region", "settlement", "interior", "neighbor", "frontier"}
    assert plan.slot("location:harbor").simulation_readiness == "navigable"
    assert plan.slot("location:harbor").presentation_readiness == "placeholder"
    assert plan.slot("location:old-road").simulation_readiness == "navigable"
    assert plan.slot("location:old-road").presentation_readiness == "assets_pending"
    assert plan.slot("location:old-road:frontier").deferred is True
    assert plan.metadata["optional_art_never_blocks_navigation"] is True


def test_placeholder_maps_are_navigable_and_predict_deferred_materialization() -> None:
    plan = build_starter_bubble(
        world_id="world:starter",
        source_world_revision=2,
        starting_location_id="location:harbor",
        neighboring_location_id="location:old-road",
    )
    definitions = build_starter_map_definitions(
        plan,
        target_world_revision=3,
    )
    certification = starter_bubble_certification(plan, definitions)
    queue = predictive_materialization_queue(
        plan,
        current_location_id="location:harbor",
    )

    assert len(definitions) == 3
    assert {definition.metadata["starter_role"] for definition in definitions} == {
        "settlement",
        "interior",
        "neighbor",
    }
    assert all(definition.is_walkable((4, 4)) for definition in definitions)
    assert all(definition.definition_hash.startswith("sha256:") for definition in definitions)
    assert all(
        definition.semantic_interface_hash.startswith("sha256:")
        for definition in definitions
    )
    assert certification["simulation_certified"] is True
    assert certification["presentation_complete"] is False
    assert certification["optional_art_blocks_gameplay"] is False
    assert queue == (
        {
            "location_id": "location:old-road:frontier",
            "map_id": "map:location:old-road:frontier:frontier",
            "priority": 0.45,
            "resource_class": "cpu",
            "presentation_optional": True,
            "fallback": "navigable_placeholder",
        },
    )


def test_optional_art_failure_does_not_invalidate_simulation_certification() -> None:
    plan = build_starter_bubble(
        world_id="world:starter",
        source_world_revision=1,
        starting_location_id="location:harbor",
    )
    failed_slots = tuple(
        slot.model_copy(update={"presentation_readiness": "failed"})
        if slot.role == "neighbor"
        else slot
        for slot in plan.slots
    )
    failed_art_plan = plan.model_copy(update={"slots": failed_slots})
    definitions = build_starter_map_definitions(
        failed_art_plan,
        target_world_revision=2,
    )
    certification = starter_bubble_certification(failed_art_plan, definitions)

    assert certification["simulation_certified"] is True
    assert certification["presentation_complete"] is False
    assert certification["optional_art_blocks_gameplay"] is False
