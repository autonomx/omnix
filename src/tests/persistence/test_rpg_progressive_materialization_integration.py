from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.unit_of_work import unit_of_work
from app.rpg.worlds.contracts import WorldReleaseDocument, WorldRevisionDocument
from app.rpg.worlds.progressive_materialization import materialize_deferred_location
from app.rpg.worlds.service import (
    compile_scenario_revision,
    compile_world_release,
    compile_world_revision,
    resolve_campaign_binding,
)
from app.rpg.worlds.starter_bubble_service import promote_starter_bubble

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)

_NEIGHBOR_MAP_ID = "map:location:old-road:neighbor"
_FRONTIER_MAP_ID = "map:location:old-road:frontier:frontier"


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=3,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-rpg-progressive-materialization",
        )
    )


def _reset(database: PostgresDatabase) -> None:
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_rpg_world_generation_runs, "
            "omnix_rpg_campaign_map_events, omnix_rpg_campaign_map_instances, "
            "omnix_rpg_map_definitions, omnix_rpg_campaign_world_bindings, "
            "omnix_rpg_scenario_revisions, omnix_rpg_scenarios, "
            "omnix_rpg_world_releases, omnix_rpg_world_revisions, "
            "omnix_rpg_world_topics, omnix_rpg_worlds, "
            "omnix_rpg_campaign_genesis_runs, omnix_rpg_narrative_responses, "
            "omnix_rpg_hermes_research, omnix_rpg_world_forge_proposals, "
            "omnix_rpg_campaign_bible_revisions, omnix_rpg_campaign_bibles, "
            "omnix_rpg_participants, omnix_rpg_snapshots, omnix_rpg_interactions, "
            "omnix_rpg_turns, omnix_rpg_campaigns, omnix_job_attempts, "
            "omnix_job_events, omnix_jobs, omnix_outbox_events, omnix_audit_events, "
            "omnix_workspace_memberships, omnix_workspaces, omnix_users CASCADE"
        )


def test_deferred_materialization_creates_future_release_without_upgrading_campaign() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        source_revision = compile_world_revision(
            world_id="world:progressive",
            revision=1,
            title="Progressive World",
            canon={"campaign_template": "classic_fantasy"},
            entity_manifest={"locations": ["location:harbor"]},
            topology={"locations": ["location:harbor"], "routes": []},
        )
        source_release = compile_world_release(
            source_revision,
            release=1,
            certification={"launch_ready": True, "missing_requirements": []},
        )
        with unit_of_work(database) as work:
            work.world_scenarios.create_world(
                context,
                world_id="world:progressive",
                title="Progressive World",
                source_mode="hybrid",
                genre="classic_fantasy",
                tone="heroic adventure",
                metadata={"starting_location": "location:harbor"},
            )
            work.world_scenarios.publish_world_revision(
                context,
                world_id="world:progressive",
                document=source_revision.model_dump(mode="json"),
                content_hash=source_revision.content_hash,
                expected_revision=0,
            )
            work.world_scenarios.publish_world_release(
                context,
                world_id="world:progressive",
                world_revision=1,
                document=source_release.model_dump(mode="json"),
                release_hash=source_release.release_hash,
            )
            work.commit()

        starter = promote_starter_bubble(
            world_id="world:progressive",
            source_world_revision=1,
            starting_location_id="location:harbor",
            neighboring_location_id="location:old-road",
            database=database,
        )
        assert starter["status"] == "ready"
        assert starter["promotion"]["world_revision"] == 2

        with unit_of_work(database) as work:
            revision_row = work.world_scenarios.get_world_revision(
                context,
                "world:progressive",
                2,
            )
            release_row = work.world_scenarios.get_world_release(
                context,
                "world:progressive",
                2,
                1,
            )
            work.rollback()
        assert revision_row is not None
        assert release_row is not None
        starter_revision = WorldRevisionDocument.model_validate(
            revision_row["document"]
        )
        starter_release = WorldReleaseDocument.model_validate(
            release_row["document"]
        )
        scenario = compile_scenario_revision(
            scenario_id="scenario:starter",
            revision=1,
            world_revision=starter_revision,
            compatible_release=starter_release.release,
            starting_location_id="location:harbor",
        )
        binding = resolve_campaign_binding(
            campaign_id="campaign:starter",
            world_revision=starter_revision,
            world_release=starter_release,
            scenario_revision=scenario,
        )
        pinned_neighbor_hash = binding.map_definition_pins[_NEIGHBOR_MAP_ID]
        with unit_of_work(database) as work:
            work.world_scenarios.create_scenario(
                context,
                scenario_id="scenario:starter",
                world_id="world:progressive",
                title="Starter Scenario",
                metadata={},
            )
            work.world_scenarios.publish_scenario_revision(
                context,
                scenario_id="scenario:starter",
                world_id="world:progressive",
                world_revision=2,
                document=scenario.model_dump(mode="json"),
                content_hash=scenario.content_hash,
            )
            work.rpg.create_campaign(
                context,
                campaign_id="campaign:starter",
                title="Pinned Starter Campaign",
                state={},
                engine_version="test",
                schema_version="test",
                seed="1",
                metadata={},
            )
            work.world_scenarios.bind_campaign(
                context,
                campaign_id=binding.campaign_id,
                world_id=binding.world_id,
                world_revision=binding.world_revision,
                world_release=binding.world_release,
                scenario_id=binding.scenario_id,
                scenario_revision=binding.scenario_revision,
                binding=binding.model_dump(mode="json"),
            )
            work.commit()

        materialized = materialize_deferred_location(
            world_id="world:progressive",
            source_world_revision=2,
            location_id="location:old-road:frontier",
            database=database,
        )
        repeated = materialize_deferred_location(
            world_id="world:progressive",
            source_world_revision=2,
            location_id="location:old-road:frontier",
            database=database,
        )

        assert materialized["ok"] is True
        assert materialized["status"] == "ready"
        assert materialized["reused"] is False
        result = materialized["materialization"]
        assert result["world_revision"] == 3
        assert result["world_release"] == 1
        assert result["location_id"] == "location:old-road:frontier"
        assert result["map_binding"]["simulation_readiness"] == "navigable"
        assert result["map_binding"]["presentation_readiness"] == "assets_pending"
        assert {row["map_id"] for row in result["map_bindings"]} == {
            _NEIGHBOR_MAP_ID,
            _FRONTIER_MAP_ID,
        }
        assert len(result["map_definitions"]) == 2
        assert set(
            result["certification"]["progressive_materialization"][
                "affected_map_ids"
            ]
        ) == {_NEIGHBOR_MAP_ID, _FRONTIER_MAP_ID}
        assert result["certification"]["optional_art_blocks_gameplay"] is False
        assert repeated["reused"] is True
        assert repeated["materialization"]["world_revision"] == 3

        with unit_of_work(database) as work:
            future_release = work.world_scenarios.get_world_release(
                context,
                "world:progressive",
                3,
                1,
            )
            pinned = work.world_scenarios.get_campaign_binding(
                context,
                "campaign:starter",
            )
            map_count = work.connection.execute(
                "SELECT COUNT(*) FROM omnix_rpg_map_definitions "
                "WHERE workspace_id = %s AND world_id = %s",
                (context.workspace_id, "world:progressive"),
            ).fetchone()[0]
            work.rollback()

        assert future_release is not None
        future_bindings = {
            row["map_id"]: row
            for row in future_release["document"]["map_bindings"]
        }
        assert len(future_bindings) == 4
        assert future_bindings[_NEIGHBOR_MAP_ID]["definition_hash"] != pinned_neighbor_hash
        assert future_bindings[_FRONTIER_MAP_ID]["simulation_readiness"] == "navigable"
        assert map_count == 5
        assert pinned is not None
        assert pinned["world_revision"] == 2
        assert pinned["world_release"] == 1
        assert len(pinned["map_definition_pins"]) == 3
        assert pinned["map_definition_pins"][_NEIGHBOR_MAP_ID] == pinned_neighbor_hash
    finally:
        database.close()
