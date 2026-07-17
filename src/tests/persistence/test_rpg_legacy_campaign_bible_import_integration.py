from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.unit_of_work import unit_of_work
from app.rpg.worlds.contracts import (
    ScenarioRevisionDocument,
    WorldReleaseDocument,
    WorldRevisionDocument,
)
from app.rpg.worlds.legacy_bible_import import (
    LEGACY_BIBLE_IMPORT_VERSION,
    import_campaign_bible_as_world,
    legacy_import_ids,
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
            application_name="omnix-rpg-legacy-bible-import",
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


def _bible_document(campaign_id: str) -> dict:
    completeness = {
        "score": 1.0,
        "documents": 1,
        "entities": 2,
        "facts": 1,
        "relationships": 1,
        "retrieval_cards": 1,
        "opening_location_ids": ["location:rusty_flagon"],
        "opening_actor_ids": ["npc:bran"],
        "missing_requirements": [],
    }
    return {
        "schema_version": "rpg_campaign_bible_v2",
        "campaign_id": campaign_id,
        "campaign_template": "classic_fantasy",
        "canon_revision": 1,
        "manifest": {
            "document_count": 1,
            "entity_count": 2,
            "fact_count": 1,
            "relationship_count": 1,
            "retrieval_card_count": 1,
        },
        "documents": [
            {
                "document_id": "document:rusty_flagon",
                "title": "The Rusty Flagon",
                "summary_120": "A crowded roadside tavern.",
                "visibility": "public",
                "entities": ["location:rusty_flagon", "npc:bran"],
            }
        ],
        "entities": {
            "location:rusty_flagon": {
                "id": "location:rusty_flagon",
                "kind": "location",
                "name": "The Rusty Flagon",
                "visibility": "public",
            },
            "npc:bran": {
                "id": "npc:bran",
                "kind": "npc",
                "name": "Bran",
                "location_id": "location:rusty_flagon",
                "dossier_status": "complete",
                "visibility": "player_known",
            },
        },
        "facts": [
            {
                "id": "fact:bran_owns_tavern",
                "content": "Bran owns the Rusty Flagon.",
                "entity_refs": ["npc:bran", "location:rusty_flagon"],
                "visibility": "player_known",
            }
        ],
        "relationships": [
            {
                "id": "route:rusty_flagon:old_road",
                "kind": "route",
                "source_id": "location:rusty_flagon",
                "target_id": "location:old_road",
            }
        ],
        "knowledge_rules": [],
        "story_threads": [
            {
                "id": "seed:missing_keg",
                "title": "The Missing Keg",
                "location_ids": ["location:rusty_flagon"],
                "actor_ids": ["npc:bran"],
            }
        ],
        "retrieval_cards": [
            {
                "id": "card:rusty_flagon",
                "title": "The Rusty Flagon",
                "content": "A roadside tavern owned by Bran.",
                "entity_refs": ["location:rusty_flagon", "npc:bran"],
            }
        ],
        "indexes": {
            "index_version": "rpg_campaign_retrieval_index_v1",
            "card_count": 1,
            "lexical": {"tavern": ["card:rusty_flagon"]},
            "entities": {
                "npc:bran": {
                    "name": "Bran",
                    "kind": "npc",
                    "retrieval_card_ids": ["card:rusty_flagon"],
                }
            },
        },
        "discovery_state": {
            "pages": {"document:rusty_flagon": "public_at_campaign_start"},
            "entities": {
                "location:rusty_flagon": "partially_known",
                "npc:bran": "partially_known",
            },
            "discoveries": [],
        },
        "consistency_report": {"passed": True, "issues": []},
        "completeness": completeness,
        "generation_provenance": {"realm": {"provider": "legacy-test"}},
    }


def test_persisted_campaign_bible_imports_once_without_rebinding_campaign() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        campaign_id = "campaign:legacy-import"
        document = _bible_document(campaign_id)
        completeness = dict(document["completeness"])
        consistency = dict(document["consistency_report"])
        with unit_of_work(database) as work:
            campaign = work.rpg.create_campaign(
                context,
                campaign_id=campaign_id,
                title="Legacy Ashen Coast",
                state={"location_id": "location:rusty_flagon"},
                engine_version="legacy-import-test",
                schema_version="rpg-session-v1",
                seed="17",
                metadata={"genre": "classic_fantasy", "tone": "grim coastal"},
            )
            bible = work.campaign_bibles.put(
                context,
                campaign_id=campaign_id,
                document=document,
                expected_revision=0,
                provenance={"generator": "legacy-world-forge", "prompt": "v7"},
                consistency_report=consistency,
                completeness=completeness,
            )
            work.commit()

        imported = import_campaign_bible_as_world(campaign_id, database=database)
        repeated = import_campaign_bible_as_world(campaign_id, database=database)
        world_id, scenario_id = legacy_import_ids(campaign_id)

        assert imported["ok"] is True
        assert imported["reused"] is False
        assert imported["source_campaign_rebound"] is False
        assert repeated["reused"] is True
        assert repeated["source_campaign_rebound"] is False
        assert imported["world"]["id"] == world_id
        assert imported["world"]["source_mode"] == "imported"

        with unit_of_work(database) as work:
            stored_world = work.world_scenarios.get_world(context, world_id)
            stored_revision = work.world_scenarios.get_world_revision(
                context,
                world_id,
                1,
            )
            stored_release = work.world_scenarios.get_world_release(
                context,
                world_id,
                1,
                1,
            )
            stored_scenario = work.world_scenarios.get_scenario_revision(
                context,
                scenario_id,
                1,
            )
            source_campaign = work.rpg.get_campaign(context, campaign_id)
            source_bible = work.campaign_bibles.get(context, campaign_id)
            source_binding = work.world_scenarios.get_campaign_binding(
                context,
                campaign_id,
            )
            work.rollback()

        assert stored_world is not None and stored_world["status"] == "published"
        assert stored_revision is not None
        revision = WorldRevisionDocument.model_validate(stored_revision["document"])
        assert revision.canon == document
        provenance = revision.provenance["legacy_campaign_bible_import"]
        assert provenance["import_version"] == LEGACY_BIBLE_IMPORT_VERSION
        assert provenance["source_campaign_id"] == campaign_id
        assert provenance["source_campaign_revision"] == campaign["revision"]
        assert provenance["source_campaign_state_hash"] == campaign["state_hash"]
        assert provenance["source_bible_revision"] == bible["revision"]
        assert provenance["source_bible_hash"] == f"sha256:{bible['content_hash']}"
        assert provenance["source_bible_provenance"] == {
            "generator": "legacy-world-forge",
            "prompt": "v7",
        }
        assert revision.entity_manifest["entities"]["npc:bran"]["name"] == "Bran"
        assert revision.topology["locations"] == ["location:rusty_flagon"]
        assert revision.topology["routes"][0]["id"] == (
            "route:rusty_flagon:old_road"
        )
        assert revision.blueprint_requirements[0]["map_id"] == (
            "map:location:rusty_flagon"
        )

        assert stored_release is not None
        release = WorldReleaseDocument.model_validate(stored_release["document"])
        assert release.indexes == document["indexes"]
        assert release.certification["launch_ready"] is False
        assert release.certification["missing_requirements"] == [
            "legacy_map_compilation_required"
        ]
        assert release.certification["source_bible_hash"] == (
            f"sha256:{bible['content_hash']}"
        )

        assert stored_scenario is not None
        scenario = ScenarioRevisionDocument.model_validate(stored_scenario["document"])
        assert scenario.starting_location_id == "location:rusty_flagon"
        assert scenario.initial_npc_ids == ("npc:bran",)
        assert scenario.opening_seed_ids == ("seed:missing_keg",)
        assert scenario.compatible_release is None

        assert source_campaign is not None
        assert source_campaign["state_hash"] == campaign["state_hash"]
        assert source_bible is not None
        assert source_bible["revision"] == bible["revision"]
        assert source_bible["content_hash"] == bible["content_hash"]
        assert source_bible["document"] == document
        assert source_binding is None
    finally:
        database.close()
