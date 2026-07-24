from app.rpg.session.genesis.world_forge_generation import (
    GeneratedTopic,
    WorldForgeGenerationResult,
)
from app.rpg.worlds.canon_repair import normalize_generation_contracts
from app.rpg.worlds.map_blueprint_publication import merge_authored_blueprints
from app.rpg.worlds.service import compile_world_release, compile_world_revision


def test_authored_map_merge_preserves_runtime_artifacts() -> None:
    revision = compile_world_revision(
        world_id="world:test",
        revision=1,
        title="Test World",
        canon={"entities": {}},
        entity_manifest={},
        topology={},
    )
    runtime_seed = {
        "schema_version": "rpg_world_runtime_seed_v1",
        "content_hash": "sha256:runtime",
        "passed": True,
    }
    materialization = {
        "schema_version": "rpg_vertical_slice_materialization_v1",
        "content_hash": "sha256:materialization",
        "passed": True,
    }
    playtest = {
        "schema_version": "rpg_player_absent_playtest_v1",
        "content_hash": "sha256:playtest",
        "passed": True,
    }
    release = compile_world_release(
        revision,
        release=1,
        artifact_stage="playtested",
        runtime_seed=runtime_seed,
        materialization=materialization,
        playtest_report=playtest,
        certification={"launch_ready": True},
    )

    _, merged = merge_authored_blueprints(
        revision,
        release,
        [
            {
                "map_id": "map:hub",
                "blueprint_revision": 1,
                "blueprint_hash": "sha256:blueprint",
                "semantic_interface_hash": "sha256:interface",
                "simulation_readiness": "navigable",
                "presentation_readiness": "placeholder",
            }
        ],
    )

    assert merged.artifact_stage == "playtested"
    assert merged.runtime_seed == runtime_seed
    assert merged.materialization == materialization
    assert merged.playtest_report == playtest
    assert merged.certification["launch_ready"] is True


def test_representation_normalization_records_field_level_provenance() -> None:
    topic = GeneratedTopic(
        topic_id="actors",
        documents=(
            {
                "id": "document:ada",
                "content": "Ada repairs tidal relays.",
            },
        ),
        entities=(
            {
                "entity_id": "actor:ada",
                "title": "Ada",
                "kind": "actor",
            },
        ),
        facts=(
            {
                "fact_id": "fact:ada:goal",
                "statement": "Ada repairs tidal relays.",
            },
        ),
        relationships=(
            {
                "relationship_id": "relationship:ada:harbor",
                "source_entity_id": "actor:ada",
                "target_entity_id": "place:harbor",
            },
        ),
        provenance={"generator": "world_library_manual_authoring"},
    )
    normalized = normalize_generation_contracts(
        WorldForgeGenerationResult(topics=(topic,))
    ).topics[0]

    actions = normalized.provenance["publication_normalization_actions"]
    changed_fields = {
        (action["collection"], action["field"])
        for action in actions
    }
    assert ("entities", "id") in changed_fields
    assert ("entities", "name") in changed_fields
    assert ("documents", "document_id") in changed_fields
    assert ("documents", "full_text") in changed_fields
    assert ("facts", "id") in changed_fields
    assert ("facts", "content") in changed_fields
    assert ("relationships", "id") in changed_fields
    assert ("relationships", "source_id") in changed_fields
    assert ("relationships", "target_id") in changed_fields
    assert all(action["semantic_change"] is False for action in actions)
    assert normalized.provenance["publication_normalization_action_count"] == len(
        actions
    )
