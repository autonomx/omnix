from __future__ import annotations

import pytest

from app.rpg.map_grid_contracts import (
    GridActorPlacement,
    GridMapDefinition,
    GridPortal,
    GridPortalEndpoint,
    GridSpawnPoint,
    GridTransform,
    GridZone,
    TerrainRule,
    with_grid_definition_hashes,
)
from app.rpg.map_instance_runtime import (
    MapMovementError,
    MoveActorCommand,
    create_map_instance_snapshot,
    project_observer_map,
    replay_map_events,
    resolve_move_command,
)


def _tavern_definition() -> GridMapDefinition:
    rows = ["#" * 30]
    rows.extend("#" + "." * 28 + "#" for _ in range(28))
    rows.append("#" * 30)
    base = GridMapDefinition(
        map_id="interior:rusty_flagon:ground_floor",
        level="interior",
        definition_revision=1,
        world_id="world:shared",
        world_revision=1,
        width=30,
        height=30,
        transform=GridTransform(
            cell_width=32,
            cell_height=32,
            display_offset_x=1,
            display_offset_y=1,
        ),
        terrain_palette=(
            TerrainRule(
                code=".",
                terrain_id="wood_floor",
                walkable=True,
                movement_cost=10,
            ),
            TerrainRule(
                code="#",
                terrain_id="stone_wall",
                walkable=False,
                movement_cost=10,
                blocks_sight=True,
            ),
        ),
        terrain_rows=tuple(rows),
        portals=(
            GridPortal(
                portal_id="portal:front_door",
                source=GridPortalEndpoint(
                    map_id="interior:rusty_flagon:ground_floor",
                    cell=(14, 28),
                ),
                target=GridPortalEndpoint(
                    map_id="settlement:greyhaven",
                    cell=(42, 31),
                ),
            ),
            GridPortal(
                portal_id="portal:secret_cellar",
                source=GridPortalEndpoint(
                    map_id="interior:rusty_flagon:ground_floor",
                    cell=(20, 22),
                ),
                target=GridPortalEndpoint(
                    map_id="interior:rusty_flagon:cellar",
                    cell=(6, 3),
                ),
                secret=True,
            ),
        ),
        spawn_points=(
            GridSpawnPoint(
                spawn_point_id="spawn:common_room",
                cell=(14, 14),
            ),
        ),
        zones=(
            GridZone(
                zone_id="zone:common_room",
                name="Common Room",
                cells=((14, 14), (13, 13), (12, 12)),
            ),
        ),
    )
    return with_grid_definition_hashes(base)


def test_grid_definition_has_independent_hash_and_coordinate_transform() -> None:
    definition = _tavern_definition()

    assert definition.definition_hash.startswith("sha256:")
    assert definition.semantic_interface_hash.startswith("sha256:")
    assert definition.transform.display_point((14, 14)) == (15, 15)
    assert definition.transform.display_point((13, 13)) == (14, 14)
    assert definition.transform.visual_point((13, 13)) == (416, 416)


def test_actor_move_is_resolved_once_and_replays_without_pathfinding() -> None:
    definition = _tavern_definition()
    initial = create_map_instance_snapshot(
        map_instance_id="campaign:a:map:tavern",
        campaign_id="campaign:a",
        location_id="location:rusty_flagon",
        definition=definition,
        actors=(
            GridActorPlacement(
                actor_id="npc:xylvanna",
                cell=(14, 14),
                facing="northwest",
            ),
            GridActorPlacement(actor_id="player:kael", cell=(14, 12)),
        ),
    )
    event, updated = resolve_move_command(
        definition,
        initial,
        MoveActorCommand(
            command_id="command:xylvanna:1",
            actor_id="npc:xylvanna",
            destination=(13, 13),
            expected_map_state_revision=0,
        ),
    )

    assert event.from_cell == (14, 14)
    assert event.to_cell == (13, 13)
    assert event.path == ((14, 14), (13, 13))
    assert event.movement_cost == 14
    assert updated.actor("npc:xylvanna").cell == (13, 13)
    assert updated.map_state_revision == 1
    assert replay_map_events(initial, [event]) == updated


def test_stale_movement_command_is_rejected() -> None:
    definition = _tavern_definition()
    snapshot = create_map_instance_snapshot(
        map_instance_id="campaign:a:map:tavern",
        campaign_id="campaign:a",
        location_id="location:rusty_flagon",
        definition=definition,
        actors=(GridActorPlacement(actor_id="npc:xylvanna", cell=(14, 14)),),
    )

    with pytest.raises(MapMovementError, match="stale_map_state_revision"):
        resolve_move_command(
            definition,
            snapshot,
            MoveActorCommand(
                command_id="command:stale",
                actor_id="npc:xylvanna",
                destination=(13, 13),
                expected_map_state_revision=7,
            ),
        )


def test_observer_projection_redacts_secret_geometry_and_hidden_actors() -> None:
    definition = _tavern_definition()
    snapshot = create_map_instance_snapshot(
        map_instance_id="campaign:a:map:tavern",
        campaign_id="campaign:a",
        location_id="location:rusty_flagon",
        definition=definition,
        actors=(
            GridActorPlacement(actor_id="player:kael", cell=(14, 12)),
            GridActorPlacement(
                actor_id="npc:hidden_spy",
                cell=(10, 10),
                hidden=True,
            ),
        ),
    )
    projection = project_observer_map(
        definition,
        snapshot,
        observer_actor_id="player:kael",
    )

    assert [row["portal_id"] for row in projection["portals"]] == [
        "portal:front_door"
    ]
    assert [row["actor_id"] for row in projection["actors"]] == ["player:kael"]
