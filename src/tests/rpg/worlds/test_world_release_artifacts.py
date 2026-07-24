from app.rpg.session.genesis.world_forge_generation import (
    GeneratedTopic,
    WorldForgeGenerationResult,
)
from app.rpg.worlds.canon_repair import normalize_generation_contracts
from app.rpg.worlds.contracts import (
    VerticalSliceMaterializationDocument if False else WorldReleaseDocument,
    canonical_content_hash,
)
from app.rpg.worlds.map_blueprint_publication import merge_authored_blueprints
from app.rpg.worlds.runtime_seed import (
    VerticalSliceMaterializationDocument,
    compile_runtime_seed,
    run_player_absent_playtest,
)
from app.rpg.worlds.semantic_validation import certify_world_release
from app.rpg.worlds.service import compile_world_release, compile_world_revision
from app.rpg.worlds.world_bundle import replace_identifiers


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


def _artifact_canon(actor_id: str, pressure_id: str) -> dict:
    return {
        "topic_graph": {
            "metadata": {
                "resolved_profile": {
                    "domains": [
                        {
                            "domain_id": "actors",
                            "entity_kind": "actor",
                            "semantic_roles": ["initial_actors"],
                        },
                        {
                            "domain_id": "pressures",
                            "entity_kind": "pressure",
                            "semantic_roles": ["initial_conflict"],
                        },
                    ]
                },
                "resolved_profile_hash": "sha256:profile",
                "runtime_capabilities": {"living_world": True},
            }
        },
        "entities": {
            actor_id: {
                "id": actor_id,
                "kind": "actor",
                "name": "Ada",
                "location_id": "place:source",
                "goal": "Repair the tidal warning relay before the next storm surge.",
                "dependency": "Needs a calibrated ceramic relay housing.",
                "next_action": "Inspect the eastern beacon at first light.",
            },
            pressure_id: {
                "id": pressure_id,
                "kind": "pressure",
                "name": "Storm Surge",
                "actor_ids": [actor_id],
                "place_ids": ["place:source"],
                "current_state": "The red tide marker is already submerged.",
                "next_tick_change": "Water reaches the ferry workshop tomorrow.",
                "escalation_condition": "Escalates when the pump stops for one hour.",
            },
        },
    }


def test_release_certification_rebuilds_remapped_runtime_artifacts() -> None:
    source_canon = _artifact_canon("actor:source", "pressure:source")
    source_revision = compile_world_revision(
        world_id="world:source",
        revision=1,
        title="Source World",
        canon=source_canon,
        entity_manifest={},
        topology={},
    )
    runtime_seed = compile_runtime_seed(
        world_id=source_revision.world_id,
        world_revision=source_revision.revision,
        source_canon_hash=canonical_content_hash(source_canon),
        canon=source_canon,
        seed=7,
    )
    material_payload = {
        "world_id": source_revision.world_id,
        "world_revision": source_revision.revision,
        "runtime_seed_hash": runtime_seed.content_hash,
        "hub_location_id": "place:source",
        "sublocation_ids": (),
        "nearby_location_ids": (),
        "actor_ids": ("actor:source",),
        "group_ids": (),
        "clock_ids": ("clock:pressure_source",),
        "resource_ids": (),
        "opening_thread_ids": (),
        "checks": {"fixture": True},
        "passed": True,
        "content_hash": "",
    }
    material_payload["content_hash"] = canonical_content_hash(material_payload)
    materialization = VerticalSliceMaterializationDocument.model_validate(
        material_payload
    )
    playtest = run_player_absent_playtest(runtime_seed, days=7)
    source_release = compile_world_release(
        source_revision,
        release=1,
        artifact_stage="playtested",
        runtime_seed=runtime_seed.model_dump(mode="json"),
        materialization=materialization.model_dump(mode="json"),
        playtest_report=playtest.model_dump(mode="json"),
        certification={"launch_ready": True, "missing_requirements": []},
    )

    target_canon = replace_identifiers(
        source_canon,
        {
            "actor:source": "actor:clone",
            "pressure:source": "pressure:clone",
            "place:source": "place:clone",
        },
    )
    target_revision = compile_world_revision(
        world_id="world:clone",
        revision=1,
        title="Cloned World",
        canon=target_canon,
        entity_manifest={},
        topology={},
    )
    raw = replace_identifiers(
        source_release.model_dump(mode="json"),
        {
            "world:source": "world:clone",
            "actor:source": "actor:clone",
            "pressure:source": "pressure:clone",
            "place:source": "place:clone",
        },
    )
    raw.update(
        {
            "world_id": "world:clone",
            "world_revision_hash": target_revision.content_hash,
            "release_hash": "",
        }
    )
    stale_release = WorldReleaseDocument.model_validate(raw)
    certified = certify_world_release(target_revision, stale_release, {})

    assert certified.runtime_seed["world_id"] == "world:clone"
    assert certified.runtime_seed["agents"][0]["agent_id"] == "actor:clone"
    assert certified.runtime_seed["source_canon_hash"] == canonical_content_hash(
        target_canon
    )
    assert certified.runtime_seed["content_hash"] != runtime_seed.content_hash
    assert certified.materialization["runtime_seed_hash"] == certified.runtime_seed[
        "content_hash"
    ]
    assert certified.materialization["actor_ids"] == ["actor:clone"]
    assert certified.playtest_report["runtime_seed_hash"] == certified.runtime_seed[
        "content_hash"
    ]
    assert certified.playtest_report["direct_final_state_hash"] == certified.playtest_report[
        "reloaded_final_state_hash"
    ]
    assert certified.playtest_report["daily_events"][0]["events"][0][
        "agent_id"
    ] == "actor:clone"
    assert certified.certification["runtime_seed_hash"] == certified.runtime_seed[
        "content_hash"
    ]


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
        WorldForgeGenerationResult(
            topics=(topic,),
            jobs=(),
            failed_topic_ids=(),
            generation_order=(("actors",),),
        )
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
