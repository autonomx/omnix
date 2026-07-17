from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.unit_of_work import unit_of_work
from app.rpg.map_grid_contracts import (
    GridActorPlacement,
    GridMapDefinition,
    GridSpawnPoint,
    TerrainRule,
    with_grid_definition_hashes,
)
from app.rpg.map_instance_runtime import (
    ActorMovedEvent,
    CampaignMapInstanceSnapshot,
    MoveActorCommand,
    create_map_instance_snapshot,
    replay_map_events,
    resolve_move_command,
)
from app.rpg.worlds.contracts import MapDefinitionBinding
from app.rpg.worlds.service import (
    compile_scenario_revision,
    compile_world_release,
    compile_world_revision,
    resolve_campaign_binding,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=3,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-rpg-map-instance-golden-slice",
        )
    )


def _reset(database: PostgresDatabase) -> None:
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_rpg_campaign_map_events, "
            "omnix_rpg_campaign_map_instances, omnix_rpg_map_definitions, "
            "omnix_rpg_campaign_world_bindings, omnix_rpg_scenario_revisions, "
            "omnix_rpg_scenarios, omnix_rpg_world_releases, "
            "omnix_rpg_world_revisions, omnix_rpg_world_topics, omnix_rpg_worlds, "
            "omnix_rpg_campaign_genesis_runs, omnix_rpg_narrative_responses, "
            "omnix_rpg_hermes_research, omnix_rpg_world_forge_proposals, "
            "omnix_rpg_campaign_bible_revisions, omnix_rpg_campaign_bibles, "
            "omnix_rpg_participants, omnix_rpg_snapshots, omnix_rpg_interactions, "
            "omnix_rpg_turns, omnix_rpg_campaigns, omnix_outbox_events, "
            "omnix_audit_events, omnix_workspace_memberships, omnix_workspaces, "
            "omnix_users CASCADE"
        )


def _definition(*, world_revision: int, definition_revision: int) -> GridMapDefinition:
    rows = ["#" * 30]
    rows.extend("#" + "." * 28 + "#" for _ in range(28))
    rows.append("#" * 30)
    return with_grid_definition_hashes(
        GridMapDefinition(
            map_id="interior:rusty_flagon:ground_floor",
            level="interior",
            definition_revision=definition_revision,
            world_id="world:golden",
            world_revision=world_revision,
            width=30,
            height=30,
            terrain_palette=(
                TerrainRule(code=".", terrain_id="wood_floor", walkable=True),
                TerrainRule(code="#", terrain_id="wall", walkable=False),
            ),
            terrain_rows=tuple(rows),
            spawn_points=(
                GridSpawnPoint(
                    spawn_point_id="spawn:common_room",
                    cell=(14, 14),
                ),
            ),
        )
    )


def test_two_campaigns_share_definition_but_never_mutable_map_state() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        definition_v1 = _definition(world_revision=1, definition_revision=1)
        world_v1 = compile_world_revision(
            world_id="world:golden",
            revision=1,
            title="Golden World",
            canon={"realm": {"name": "Golden World"}},
            entity_manifest={"locations": [{"id": "location:rusty_flagon"}]},
            topology={"locations": ["location:rusty_flagon"], "routes": []},
            blueprint_requirements=[
                {"map_id": definition_v1.map_id, "spawn_ids": ["spawn:common_room"]}
            ],
        )
        release_v1 = compile_world_release(
            world_v1,
            release=1,
            map_bindings=[
                MapDefinitionBinding(
                    map_id=definition_v1.map_id,
                    blueprint_revision=1,
                    definition_revision=1,
                    definition_hash=definition_v1.definition_hash,
                    semantic_interface_hash=definition_v1.semantic_interface_hash,
                )
            ],
            certification={"passed": True},
        )
        scenario_v1 = compile_scenario_revision(
            scenario_id="scenario:golden_tavern",
            revision=1,
            world_revision=world_v1,
            compatible_release=1,
            starting_location_id="location:rusty_flagon",
            initial_npc_ids=["npc:xylvanna"],
        )
        bindings = {
            campaign_id: resolve_campaign_binding(
                campaign_id=campaign_id,
                world_revision=world_v1,
                world_release=release_v1,
                scenario_revision=scenario_v1,
            )
            for campaign_id in ("campaign:a", "campaign:b")
        }
        initial_snapshots = {
            campaign_id: create_map_instance_snapshot(
                map_instance_id=f"{campaign_id}:map:rusty_flagon",
                campaign_id=campaign_id,
                location_id="location:rusty_flagon",
                definition=definition_v1,
                actors=(
                    GridActorPlacement(actor_id="npc:xylvanna", cell=(14, 14)),
                    GridActorPlacement(actor_id=f"player:{campaign_id[-1]}", cell=(14, 12)),
                ),
            )
            for campaign_id in bindings
        }

        with unit_of_work(database) as work:
            work.world_scenarios.create_world(
                context, world_id="world:golden", title="Golden World"
            )
            work.world_scenarios.publish_world_revision(
                context,
                world_id="world:golden",
                document=world_v1.model_dump(mode="json"),
                content_hash=world_v1.content_hash,
                expected_revision=0,
            )
            work.map_instances.put_definition(
                context,
                map_id=definition_v1.map_id,
                definition_revision=1,
                world_id="world:golden",
                world_revision=1,
                document=definition_v1.model_dump(mode="json"),
                definition_hash=definition_v1.definition_hash,
                semantic_interface_hash=definition_v1.semantic_interface_hash,
            )
            work.world_scenarios.publish_world_release(
                context,
                world_id="world:golden",
                world_revision=1,
                document=release_v1.model_dump(mode="json"),
                release_hash=release_v1.release_hash,
            )
            work.world_scenarios.create_scenario(
                context,
                scenario_id="scenario:golden_tavern",
                world_id="world:golden",
                title="Golden Tavern",
            )
            work.world_scenarios.publish_scenario_revision(
                context,
                scenario_id="scenario:golden_tavern",
                world_id="world:golden",
                world_revision=1,
                document=scenario_v1.model_dump(mode="json"),
                content_hash=scenario_v1.content_hash,
            )
            for campaign_id, binding in bindings.items():
                work.rpg.create_campaign(
                    context,
                    campaign_id=campaign_id,
                    title=campaign_id,
                    state={"title": campaign_id},
                    engine_version="map-instance-golden-v1",
                    schema_version="rpg-session-v1",
                    seed="0",
                    metadata={},
                )
                work.world_scenarios.bind_campaign(
                    context,
                    campaign_id=campaign_id,
                    world_id=binding.world_id,
                    world_revision=binding.world_revision,
                    world_release=binding.world_release,
                    scenario_id=binding.scenario_id,
                    scenario_revision=binding.scenario_revision,
                    binding=binding.model_dump(mode="json"),
                )
                snapshot = initial_snapshots[campaign_id]
                work.map_instances.create_instance(
                    context,
                    map_instance_id=snapshot.map_instance_id,
                    campaign_id=campaign_id,
                    location_id=snapshot.location_id,
                    map_id=snapshot.map_id,
                    definition_revision=snapshot.definition_revision,
                    definition_hash=snapshot.definition_hash,
                    snapshot=snapshot.model_dump(mode="json"),
                )
            work.commit()

        initial_a = initial_snapshots["campaign:a"]
        event, updated_a = resolve_move_command(
            definition_v1,
            initial_a,
            MoveActorCommand(
                command_id="command:xylvanna:a:1",
                actor_id="npc:xylvanna",
                destination=(13, 13),
                expected_map_state_revision=0,
            ),
        )
        with unit_of_work(database) as work:
            write = work.map_instances.append_event(
                context,
                map_instance_id=initial_a.map_instance_id,
                command_id=event.command_id,
                event_id=event.event_id,
                event_type=event.event_type,
                event_sequence=event.event_sequence,
                revision_before=event.map_state_revision_before,
                revision_after=event.map_state_revision_after,
                event=event.model_dump(mode="json"),
                snapshot=updated_a.model_dump(mode="json"),
            )
            instance_b = work.map_instances.get_instance(
                context, initial_snapshots["campaign:b"].map_instance_id
            )
            work.commit()

        assert write["idempotent"] is False
        assert updated_a.actor("npc:xylvanna").cell == (13, 13)
        assert instance_b is not None
        unchanged_b = CampaignMapInstanceSnapshot.model_validate(instance_b["snapshot"])
        assert unchanged_b.actor("npc:xylvanna").cell == (14, 14)
        assert unchanged_b.map_state_revision == 0

        with unit_of_work(database) as work:
            events = [
                ActorMovedEvent.model_validate(row)
                for row in work.map_instances.list_events(
                    context, initial_a.map_instance_id
                )
            ]
            stored_a = work.map_instances.get_instance(context, initial_a.map_instance_id)
            work.rollback()
        replayed = replay_map_events(initial_a, events)
        assert stored_a is not None
        assert replayed.model_dump(mode="json") == stored_a["snapshot"]

        world_v2 = compile_world_revision(
            world_id="world:golden",
            revision=2,
            title="Golden World Revised",
            canon={"realm": {"name": "Golden World", "revision_note": "expanded"}},
            entity_manifest=world_v1.entity_manifest,
            topology=world_v1.topology,
        )
        definition_v2 = _definition(world_revision=2, definition_revision=2)
        with unit_of_work(database) as work:
            work.world_scenarios.publish_world_revision(
                context,
                world_id="world:golden",
                document=world_v2.model_dump(mode="json"),
                content_hash=world_v2.content_hash,
                expected_revision=1,
            )
            work.map_instances.put_definition(
                context,
                map_id=definition_v2.map_id,
                definition_revision=2,
                world_id="world:golden",
                world_revision=2,
                document=definition_v2.model_dump(mode="json"),
                definition_hash=definition_v2.definition_hash,
                semantic_interface_hash=definition_v2.semantic_interface_hash,
            )
            pinned_a = work.map_instances.get_instance(context, initial_a.map_instance_id)
            pinned_b = work.map_instances.get_instance(
                context, initial_snapshots["campaign:b"].map_instance_id
            )
            work.rollback()
        assert pinned_a is not None and pinned_a["definition_revision"] == 1
        assert pinned_b is not None and pinned_b["definition_revision"] == 1
        assert pinned_a["definition_hash"] == definition_v1.definition_hash
        assert pinned_b["definition_hash"] == definition_v1.definition_hash
    finally:
        database.close()
