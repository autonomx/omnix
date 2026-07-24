"""Pure compilers for immutable RPG world, release, and scenario resources."""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from .contracts import (
    CampaignWorldBinding,
    MapDefinitionBinding,
    MapInitializationOperation,
    ScenarioRevisionDocument,
    WorldArtifactStage,
    WorldReleaseDocument,
    WorldRevisionDocument,
    canonical_content_hash,
)


def _hashed_payload(payload: Mapping[str, Any], hash_field: str) -> dict[str, Any]:
    value = dict(payload)
    value[hash_field] = ""
    value[hash_field] = canonical_content_hash(value)
    return value


def compile_world_revision(
    *,
    world_id: str,
    revision: int,
    title: str,
    canon: Mapping[str, Any],
    entity_manifest: Mapping[str, Any],
    topology: Mapping[str, Any],
    adventure_seeds: Iterable[Mapping[str, Any]] = (),
    blueprint_requirements: Iterable[Mapping[str, Any]] = (),
    provenance: Mapping[str, Any] | None = None,
) -> WorldRevisionDocument:
    payload = {
        "world_id": world_id,
        "revision": revision,
        "title": title,
        "canon": dict(canon),
        "entity_manifest": dict(entity_manifest),
        "topology": dict(topology),
        "adventure_seeds": tuple(dict(row) for row in adventure_seeds),
        "blueprint_requirements": tuple(dict(row) for row in blueprint_requirements),
        "provenance": dict(provenance or {}),
    }
    return WorldRevisionDocument.model_validate(
        _hashed_payload(payload, "content_hash")
    )


def compile_world_release(
    world_revision: WorldRevisionDocument,
    *,
    release: int,
    map_bindings: Iterable[MapDefinitionBinding] = (),
    indexes: Mapping[str, Any] | None = None,
    asset_bindings: Mapping[str, Any] | None = None,
    compiler_provenance: Mapping[str, Any] | None = None,
    certification: Mapping[str, Any] | None = None,
    artifact_stage: WorldArtifactStage = "canon_validated",
    runtime_seed: Mapping[str, Any] | None = None,
    materialization: Mapping[str, Any] | None = None,
    playtest_report: Mapping[str, Any] | None = None,
) -> WorldReleaseDocument:
    revision_hash = world_revision.content_hash or canonical_content_hash(world_revision)
    payload = {
        "world_id": world_revision.world_id,
        "world_revision": world_revision.revision,
        "release": release,
        "world_revision_hash": revision_hash,
        "map_bindings": tuple(
            binding.model_dump(mode="json") for binding in map_bindings
        ),
        "indexes": dict(indexes or {}),
        "asset_bindings": dict(asset_bindings or {}),
        "compiler_provenance": dict(compiler_provenance or {}),
        "certification": dict(certification or {}),
        "artifact_stage": artifact_stage,
        "runtime_seed": dict(runtime_seed or {}),
        "materialization": dict(materialization or {}),
        "playtest_report": dict(playtest_report or {}),
    }
    return WorldReleaseDocument.model_validate(
        _hashed_payload(payload, "release_hash")
    )


def compile_scenario_revision(
    *,
    scenario_id: str,
    revision: int,
    world_revision: WorldRevisionDocument,
    starting_location_id: str,
    compatible_release: int | None = None,
    starting_epoch: str = "",
    activated_conflict_ids: Iterable[str] = (),
    initial_npc_ids: Iterable[str] = (),
    protagonist_options: Iterable[Mapping[str, Any]] = (),
    starting_resources: Mapping[str, Any] | None = None,
    opening_seed_ids: Iterable[str] = (),
    map_initialization: Iterable[MapInitializationOperation] = (),
    runtime_seed_hash: str = "",
) -> ScenarioRevisionDocument:
    revision_hash = world_revision.content_hash or canonical_content_hash(world_revision)
    payload = {
        "scenario_id": scenario_id,
        "revision": revision,
        "world_id": world_revision.world_id,
        "world_revision": world_revision.revision,
        "world_revision_hash": revision_hash,
        "compatible_release": compatible_release,
        "starting_epoch": starting_epoch,
        "starting_location_id": starting_location_id,
        "activated_conflict_ids": tuple(dict.fromkeys(activated_conflict_ids)),
        "initial_npc_ids": tuple(dict.fromkeys(initial_npc_ids)),
        "protagonist_options": tuple(dict(row) for row in protagonist_options),
        "starting_resources": dict(starting_resources or {}),
        "opening_seed_ids": tuple(dict.fromkeys(opening_seed_ids)),
        "map_initialization": tuple(
            operation.model_dump(mode="json") for operation in map_initialization
        ),
        "runtime_seed_hash": runtime_seed_hash,
    }
    return ScenarioRevisionDocument.model_validate(
        _hashed_payload(payload, "content_hash")
    )


def resolve_campaign_binding(
    *,
    campaign_id: str,
    world_revision: WorldRevisionDocument,
    world_release: WorldReleaseDocument,
    scenario_revision: ScenarioRevisionDocument,
) -> CampaignWorldBinding:
    if world_release.world_id != world_revision.world_id:
        raise ValueError("world_release_world_mismatch")
    if world_release.world_revision != world_revision.revision:
        raise ValueError("world_release_revision_mismatch")
    if world_release.world_revision_hash != world_revision.content_hash:
        raise ValueError("world_release_hash_mismatch")
    if scenario_revision.world_id != world_revision.world_id:
        raise ValueError("scenario_world_mismatch")
    if scenario_revision.world_revision != world_revision.revision:
        raise ValueError("scenario_world_revision_mismatch")
    if scenario_revision.world_revision_hash != world_revision.content_hash:
        raise ValueError("scenario_world_hash_mismatch")
    if (
        scenario_revision.compatible_release is not None
        and scenario_revision.compatible_release != world_release.release
    ):
        raise ValueError("scenario_release_incompatible")
    if (
        scenario_revision.runtime_seed_hash
        and scenario_revision.runtime_seed_hash
        != str(world_release.runtime_seed.get("content_hash") or "")
    ):
        raise ValueError("scenario_runtime_seed_hash_mismatch")

    pins = {
        binding.map_id: binding.definition_hash
        for binding in world_release.map_bindings
    }
    return CampaignWorldBinding(
        campaign_id=campaign_id,
        world_id=world_revision.world_id,
        world_revision=world_revision.revision,
        world_revision_hash=world_revision.content_hash,
        world_release=world_release.release,
        world_release_hash=world_release.release_hash,
        scenario_id=scenario_revision.scenario_id,
        scenario_revision=scenario_revision.revision,
        scenario_revision_hash=scenario_revision.content_hash,
        map_definition_pins=pins,
    )
