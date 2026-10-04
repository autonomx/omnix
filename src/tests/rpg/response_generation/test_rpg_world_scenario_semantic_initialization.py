from __future__ import annotations

import pytest

from app.rpg.map_grid_contracts import (
    GridMapDefinition,
    GridPortal,
    GridPortalEndpoint,
    GridSpawnPoint,
    TerrainRule,
    with_grid_definition_hashes,
)
from app.rpg.map_instance_runtime import project_observer_map
from app.rpg.worlds.contracts import MapDefinitionBinding, MapInitializationOperation
from app.rpg.worlds.semantic_validation import (
    WorldSemanticError,
    certify_world_release,
    initialize_starting_map_snapshot,
    validate_release_bindings,
    validate_scenario_against_release,
)
from app.rpg.worlds.service import (
    compile_scenario_revision,
    compile_world_release,
    compile_world_revision,
)


def _definition() -> GridMapDefinition:
    return with_grid_definition_hashes(
        GridMapDefinition(
            map_id="map:harbor",
            level="settlement",
            definition_revision=2,
            world_id="world:harbor",
            world_revision=1,
            width=5,
            height=5,
            terrain_palette=(
                TerrainRule(code=".", terrain_id="street", walkable=True),
            ),
            terrain_rows=(".....",) * 5,
            portals=(
                GridPortal(
                    portal_id="route:east_gate",
                    source=GridPortalEndpoint(map_id="map:harbor", cell=(4, 2)),
                    target=GridPortalEndpoint(map_id="map:road", cell=(0, 2)),
                ),
            ),
            spawn_points=(
                GridSpawnPoint(
                    spawn_point_id="spawn:arrival",
                    cell=(1, 1),
                    tags=("arrival", "player"),
                ),
                GridSpawnPoint(spawn_point_id="spawn:office", cell=(2, 1)),
            ),
            metadata={
                "location_id": "location:harbor",
                "semantic_object_ids": ["gate:eastern"],
                "semantic_hazard_ids": ["hazard:flooded_dock"],
            },
        )
    )


def _documents():
    definition = _definition()
    world = compile_world_revision(
        world_id="world:harbor",
        revision=1,
        title="Harbor World",
        canon={},
        entity_manifest={},
        topology={"locations": ["location:harbor"], "routes": []},
        blueprint_requirements=(
            {
                "map_id": definition.map_id,
                "simulation_readiness": "navigable",
                "required_before_launch": True,
            },
        ),
    )
    release = compile_world_release(
        world,
        release=1,
        map_bindings=(
            MapDefinitionBinding(
                map_id=definition.map_id,
                blueprint_revision=1,
                definition_revision=definition.definition_revision,
                definition_hash=definition.definition_hash,
                semantic_interface_hash=definition.semantic_interface_hash,
                simulation_readiness="navigable",
            ),
        ),
        certification={"launch_ready": True, "missing_requirements": []},
    )
    scenario = compile_scenario_revision(
        scenario_id="scenario:harbor",
        revision=1,
        world_revision=world,
        compatible_release=1,
        starting_location_id="location:harbor",
        initial_npc_ids=("npc:captain",),
        map_initialization=(
            MapInitializationOperation(
                operation_id="init:player",
                map_id=definition.map_id,
                type="place_actor",
                target_id="actor:protagonist",
                payload={"spawn_point_id": "spawn:arrival"},
            ),
            MapInitializationOperation(
                operation_id="init:captain",
                map_id=definition.map_id,
                type="place_actor",
                target_id="npc:captain",
                payload={"spawn_point_id": "spawn:office", "facing": "west"},
            ),
            MapInitializationOperation(
                operation_id="init:gate",
                map_id=definition.map_id,
                type="set_object_state",
                target_id="gate:eastern",
                payload={"state": "closed"},
            ),
            MapInitializationOperation(
                operation_id="init:route",
                map_id=definition.map_id,
                type="set_route_state",
                target_id="route:east_gate",
                payload={"state": "closed"},
            ),
            MapInitializationOperation(
                operation_id="init:hazard",
                map_id=definition.map_id,
                type="set_hazard_state",
                target_id="hazard:flooded_dock",
                payload={"active": True},
            ),
        ),
    )
    return definition, world, release, scenario


def test_certified_release_and_scenario_initialize_authoritative_starting_state() -> None:
    definition, world, release, scenario = _documents()
    definitions = {definition.map_id: definition}

    certified = certify_world_release(world, release, definitions)
    starting = validate_scenario_against_release(scenario, certified, definitions)
    snapshot = initialize_starting_map_snapshot(
        map_instance_id="campaign:1:map:harbor:1",
        campaign_id="campaign:1",
        protagonist_actor_id="player:campaign:1",
        scenario=scenario,
        definition=starting,
    )

    assert certified.certification["launch_ready"] is True
    assert certified.certification["semantic_validation"]["passed"] is True
    assert snapshot.actor("player:campaign:1").cell == (1, 1)
    assert snapshot.actor("npc:captain").cell == (2, 1)
    assert snapshot.object_states["gate:eastern"] == {"state": "closed"}
    assert snapshot.route_states["route:east_gate"] == {"state": "closed"}
    assert snapshot.hazard_states["hazard:flooded_dock"] == {"active": True}
    assert snapshot.map_state_revision == 0
    assert snapshot.applied_event_sequence == 0
    assert snapshot.initialization_operation_ids == (
        "init:player",
        "init:captain",
        "init:gate",
        "init:route",
        "init:hazard",
    )
    projection = project_observer_map(
        definition,
        snapshot,
        observer_actor_id="player:campaign:1",
    )
    assert "hazard_states" not in projection


def test_release_binding_hash_and_scenario_spawn_are_rejected_before_launch() -> None:
    definition, world, release, scenario = _documents()
    wrong = definition.model_copy(update={"definition_hash": "sha256:" + "f" * 64})
    with pytest.raises(WorldSemanticError, match="world_release_map_hash_mismatch"):
        validate_release_bindings(world, release, {definition.map_id: wrong})

    invalid = scenario.model_copy(
        update={
            "map_initialization": (
                MapInitializationOperation(
                    operation_id="init:missing",
                    map_id=definition.map_id,
                    type="place_actor",
                    target_id="npc:missing",
                    payload={"spawn_point_id": "spawn:missing"},
                ),
            )
        }
    )
    with pytest.raises(WorldSemanticError, match="scenario_spawn_point_missing"):
        validate_scenario_against_release(
            invalid,
            release,
            {definition.map_id: definition},
        )
