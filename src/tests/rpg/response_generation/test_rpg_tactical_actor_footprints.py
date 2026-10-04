from __future__ import annotations

import pytest

from app.rpg.map_actor_footprints import actor_footprint_cells
from app.rpg.map_geometry_patch import ApplyGeometryPatchCommand, GeometryCellPatch, resolve_geometry_patch_command
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
    replay_map_events,
    resolve_move_command,
)
from app.rpg.map_observer_runtime import ObserverPerceptionPolicy, observe_map


def _definition(rows: tuple[str, ...], *, map_id: str = "map:footprints") -> GridMapDefinition:
    return with_grid_definition_hashes(
        GridMapDefinition(
            map_id=map_id,
            level="encounter",
            definition_revision=1,
            world_id="world:footprints",
            world_revision=1,
            width=len(rows[0]),
            height=len(rows),
            terrain_palette=(
                TerrainRule(code=".", terrain_id="floor"),
                TerrainRule(
                    code="#",
                    terrain_id="wall",
                    walkable=False,
                    blocks_sight=True,
                ),
            ),
            terrain_rows=rows,
        )
    )


def test_multicell_spawn_rejects_bounds_and_overlap() -> None:
    definition = _definition((".....", ".....", ".....", "....."))
    with pytest.raises(MapMovementError, match="actor_spawn_footprint_out_of_bounds"):
        create_map_instance_snapshot(
            map_instance_id="campaign:a:map:footprints",
            campaign_id="campaign:a",
            location_id="location:footprints",
            definition=definition,
            actors=(
                GridActorPlacement(
                    actor_id="actor:large",
                    cell=(4, 3),
                    footprint_width=2,
                    footprint_height=2,
                ),
            ),
        )

    with pytest.raises(MapMovementError, match="actor_spawn_footprint_occupied"):
        create_map_instance_snapshot(
            map_instance_id="campaign:a:map:footprints",
            campaign_id="campaign:a",
            location_id="location:footprints",
            definition=definition,
            actors=(
                GridActorPlacement(
                    actor_id="actor:large",
                    cell=(1, 1),
                    footprint_width=2,
                    footprint_height=2,
                ),
                GridActorPlacement(actor_id="actor:small", cell=(2, 2)),
            ),
        )


def test_multicell_path_requires_full_width_and_replays() -> None:
    narrow = _definition(("...#...", "...#...", ".......", "...#...", "...#..."))
    large = GridActorPlacement(
        actor_id="actor:large",
        cell=(0, 1),
        footprint_width=2,
        footprint_height=2,
    )
    narrow_snapshot = create_map_instance_snapshot(
        map_instance_id="campaign:a:map:narrow",
        campaign_id="campaign:a",
        location_id="location:narrow",
        definition=narrow,
        actors=(large,),
    )
    with pytest.raises(MapMovementError, match="destination_unreachable"):
        resolve_move_command(
            narrow,
            narrow_snapshot,
            MoveActorCommand(
                command_id="move:large:narrow",
                actor_id=large.actor_id,
                destination=(5, 1),
                expected_map_state_revision=0,
            ),
        )

    wide = _definition(("...#...", ".......", ".......", "...#...", "...#..."), map_id="map:wide")
    wide_snapshot = create_map_instance_snapshot(
        map_instance_id="campaign:a:map:wide",
        campaign_id="campaign:a",
        location_id="location:wide",
        definition=wide,
        actors=(large,),
    )
    event, moved = resolve_move_command(
        wide,
        wide_snapshot,
        MoveActorCommand(
            command_id="move:large:wide",
            actor_id=large.actor_id,
            destination=(5, 1),
            expected_map_state_revision=0,
        ),
    )

    assert event.pathfinder_version == 2
    assert actor_footprint_cells(moved.actor(large.actor_id)) == (
        (5, 1),
        (6, 1),
        (5, 2),
        (6, 2),
    )
    assert replay_map_events(wide_snapshot, (event,)) == moved


def test_destination_and_geometry_patch_respect_non_anchor_cells() -> None:
    definition = _definition((".......", ".......", ".......", "......."))
    large = GridActorPlacement(
        actor_id="actor:large",
        cell=(1, 1),
        footprint_width=2,
        footprint_height=2,
    )
    blocker = GridActorPlacement(actor_id="actor:blocker", cell=(5, 2))
    snapshot = create_map_instance_snapshot(
        map_instance_id="campaign:a:map:footprints",
        campaign_id="campaign:a",
        location_id="location:footprints",
        definition=definition,
        actors=(large, blocker),
    )

    with pytest.raises(MapMovementError, match="destination_occupied"):
        resolve_move_command(
            definition,
            snapshot,
            MoveActorCommand(
                command_id="move:large:blocked",
                actor_id=large.actor_id,
                destination=(4, 1),
                expected_map_state_revision=0,
            ),
        )

    with pytest.raises(MapMovementError, match="geometry_patch_actor_occupied"):
        resolve_geometry_patch_command(
            definition,
            snapshot,
            ApplyGeometryPatchCommand(
                command_id="patch:large:non-anchor",
                patch_id="patch:large:non-anchor",
                expected_map_state_revision=0,
                cells=(GeometryCellPatch(cell=(2, 2), terrain_code="#"),),
            ),
        )


def test_observer_detects_visible_non_anchor_footprint_cell() -> None:
    definition = _definition((".......", "......."), map_id="map:visibility")
    snapshot = create_map_instance_snapshot(
        map_instance_id="campaign:a:map:visibility",
        campaign_id="campaign:a",
        location_id="location:visibility",
        definition=definition,
        actors=(
            GridActorPlacement(
                actor_id="actor:wide",
                cell=(1, 0),
                footprint_width=3,
                footprint_height=1,
            ),
            GridActorPlacement(actor_id="observer:a", cell=(6, 0)),
        ),
    )

    knowledge, _ = observe_map(
        definition,
        snapshot,
        observer_actor_id="observer:a",
        policy=ObserverPerceptionPolicy(sight_radius=3, detection_radius=1),
    )

    assert "actor:wide" in knowledge.detected_actor_ids
    assert (1, 0) not in knowledge.visible_cells
    assert (3, 0) in knowledge.visible_cells
