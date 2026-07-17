from __future__ import annotations

import pytest
from fastapi import FastAPI

from app.gateway.rpg_geometry_patch_routes import register_rpg_geometry_patch_routes
from app.rpg.map_geometry_patch import (
    ApplyGeometryPatchCommand,
    GeometryCellPatch,
    replay_campaign_map_events,
    resolve_geometry_patch_command,
)
from app.rpg.map_grid_contracts import (
    GridActorPlacement,
    GridMapDefinition,
    TerrainRule,
    with_grid_definition_hashes,
)
from app.rpg.map_instance_runtime import (
    MapMovementError,
    MoveActorCommand,
    create_map_instance_snapshot,
    resolve_move_command,
)
from app.rpg.map_observer_runtime import has_line_of_sight


def _definition() -> GridMapDefinition:
    return with_grid_definition_hashes(
        GridMapDefinition(
            map_id="map:geometry",
            level="interior",
            definition_revision=1,
            world_id="world:geometry",
            world_revision=1,
            width=5,
            height=3,
            terrain_palette=(
                TerrainRule(code=".", terrain_id="floor"),
                TerrainRule(
                    code="#",
                    terrain_id="wall",
                    walkable=False,
                    blocks_sight=True,
                ),
            ),
            terrain_rows=("..#..", "..#..", "..#.."),
        )
    )


def test_geometry_patch_changes_movement_los_and_replays() -> None:
    definition = _definition()
    initial = create_map_instance_snapshot(
        map_instance_id="campaign:a:map:geometry",
        campaign_id="campaign:a",
        location_id="location:geometry",
        definition=definition,
        actors=(GridActorPlacement(actor_id="player:a", cell=(0, 1)),),
    )
    with pytest.raises(MapMovementError, match="destination_unreachable"):
        resolve_move_command(
            definition,
            initial,
            MoveActorCommand(
                command_id="move:blocked",
                actor_id="player:a",
                destination=(4, 1),
                expected_map_state_revision=0,
            ),
        )
    assert has_line_of_sight(
        definition,
        (0, 1),
        (4, 1),
        snapshot=initial,
    ) is False

    patch_event, patched = resolve_geometry_patch_command(
        definition,
        initial,
        ApplyGeometryPatchCommand(
            command_id="geometry:open-wall",
            patch_id="patch:open-wall",
            expected_map_state_revision=0,
            cells=tuple(
                GeometryCellPatch(cell=(2, row), terrain_code=".")
                for row in range(3)
            ),
        ),
    )
    move_event, moved = resolve_move_command(
        definition,
        patched,
        MoveActorCommand(
            command_id="move:through-wall",
            actor_id="player:a",
            destination=(4, 1),
            expected_map_state_revision=1,
        ),
    )

    assert has_line_of_sight(
        definition,
        (0, 1),
        (4, 1),
        snapshot=patched,
    ) is True
    assert moved.actor("player:a").cell == (4, 1)
    assert moved.terrain_overrides == {"2,0": ".", "2,1": ".", "2,2": "."}
    assert replay_campaign_map_events(initial, (patch_event, move_event)) == moved

    clear_event, cleared = resolve_geometry_patch_command(
        definition,
        moved,
        ApplyGeometryPatchCommand(
            command_id="geometry:restore-wall",
            patch_id="patch:restore-wall",
            expected_map_state_revision=2,
            cells=tuple(
                GeometryCellPatch(cell=(2, row), terrain_code=None)
                for row in range(3)
            ),
        ),
    )
    assert clear_event.event_sequence == 3
    assert cleared.terrain_overrides == {}
    assert has_line_of_sight(
        definition,
        (0, 1),
        (4, 1),
        snapshot=cleared,
    ) is False


def test_geometry_patch_rejects_impassable_occupied_cell_and_route_is_hidden() -> None:
    definition = _definition()
    snapshot = create_map_instance_snapshot(
        map_instance_id="campaign:a:map:geometry",
        campaign_id="campaign:a",
        location_id="location:geometry",
        definition=definition,
        actors=(GridActorPlacement(actor_id="player:a", cell=(1, 1)),),
    )
    with pytest.raises(MapMovementError, match="geometry_patch_actor_occupied"):
        resolve_geometry_patch_command(
            definition,
            snapshot,
            ApplyGeometryPatchCommand(
                command_id="geometry:block-player",
                patch_id="patch:block-player",
                expected_map_state_revision=0,
                cells=(GeometryCellPatch(cell=(1, 1), terrain_code="#"),),
            ),
        )

    app = FastAPI()
    register_rpg_geometry_patch_routes(app)
    path = "/api/rpg/map-instances/{map_instance_id}/geometry-patches"
    assert path in {route.path for route in app.routes}
    assert path not in app.openapi()["paths"]

    gateway_app = FastAPI(title="Omnix Web Gateway")
    assert path in {route.path for route in gateway_app.routes}
    assert path not in gateway_app.openapi()["paths"]
