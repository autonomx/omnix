"""Deterministic ID remapping and hash rebuilding for imported world bundles."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from app.rpg.map_grid_contracts import GridMapDefinition, with_grid_definition_hashes

from .contracts import (
    ScenarioRevisionDocument,
    WorldReleaseDocument,
    WorldRevisionDocument,
    canonical_content_hash,
)
from .generation_jobs import canonical_hash
from .map_blueprint_authoring import MapBlueprintDocument
from .semantic_validation import certify_world_release
from .world_bundle import WorldBundlePayload, replace_identifiers, safe_bundle_segment


@dataclass(frozen=True)
class TransformedWorldBundle:
    payload: WorldBundlePayload
    identifier_map: dict[str, str]
    asset_id_map: dict[str, str]
    run_id_map: dict[str, str]


def _portable_id(
    kind: str,
    source_id: str,
    target_world_id: str,
    bundle_sha256: str,
    occupied: set[str],
) -> str:
    prefix = {
        "map": "map",
        "scenario": "scenario",
        "asset": "image:world-import",
        "run": "world-run:import",
    }[kind]
    base = f"{prefix}:{safe_bundle_segment(target_world_id)}:{safe_bundle_segment(source_id)}"
    candidate = base
    if candidate in occupied:
        candidate = f"{base}:{bundle_sha256[:12]}"
    index = 2
    while candidate in occupied:
        candidate = f"{base}:{bundle_sha256[:12]}:{index}"
        index += 1
    occupied.add(candidate)
    return candidate


def _mapping(
    source_ids: Iterable[str],
    *,
    kind: str,
    target_world_id: str,
    source_world_id: str,
    bundle_sha256: str,
    occupied: set[str],
) -> dict[str, str]:
    result: dict[str, str] = {}
    for source_id in sorted({str(value) for value in source_ids if str(value)}):
        if target_world_id == source_world_id and source_id not in occupied:
            occupied.add(source_id)
            result[source_id] = source_id
        else:
            result[source_id] = _portable_id(
                kind,
                source_id,
                target_world_id,
                bundle_sha256,
                occupied,
            )
    return result


def _with_hash(document: Any, field: str) -> Any:
    payload = document.model_dump(mode="json")
    payload[field] = ""
    payload[field] = canonical_content_hash(payload)
    return type(document).model_validate(payload)


def _import_metadata(
    value: Mapping[str, Any] | None,
    *,
    source_world_id: str,
    target_world_id: str,
    bundle_sha256: str,
) -> dict[str, Any]:
    result = dict(value or {})
    result["world_bundle_import"] = {
        "source_world_id": source_world_id,
        "target_world_id": target_world_id,
        "bundle_sha256": bundle_sha256,
        "format_version": 1,
    }
    return result


def transform_world_bundle(
    payload: WorldBundlePayload,
    *,
    target_world_id: str,
    bundle_sha256: str,
    existing_scenario_ids: Iterable[str] = (),
    existing_map_ids: Iterable[str] = (),
    existing_asset_ids: Iterable[str] = (),
    existing_run_ids: Iterable[str] = (),
) -> TransformedWorldBundle:
    source_world_id = str(payload.world.get("id") or "")
    if not source_world_id or not target_world_id.strip():
        raise ValueError("world_bundle_world_id_required")
    target_world_id = target_world_id.strip()

    source_map_ids = {
        str(row.get("map_id") or "")
        for row in (*payload.map_blueprints, *payload.map_definitions)
    }
    source_scenario_ids = {
        str(row.get("id") or "") for row in payload.scenarios
    } | {
        str(row.get("scenario_id") or "") for row in payload.scenario_revisions
    }
    source_asset_ids = set()
    for root in payload.model_dump(mode="json").values():
        source_asset_ids.update(_referenced_assets(root))
    source_run_ids = {
        str(row.get("run_id") or "") for row in payload.generation_runs
    }

    map_id_map = _mapping(
        source_map_ids,
        kind="map",
        target_world_id=target_world_id,
        source_world_id=source_world_id,
        bundle_sha256=bundle_sha256,
        occupied=set(existing_map_ids),
    )
    scenario_id_map = _mapping(
        source_scenario_ids,
        kind="scenario",
        target_world_id=target_world_id,
        source_world_id=source_world_id,
        bundle_sha256=bundle_sha256,
        occupied=set(existing_scenario_ids),
    )
    asset_id_map = _mapping(
        source_asset_ids,
        kind="asset",
        target_world_id=target_world_id,
        source_world_id=source_world_id,
        bundle_sha256=bundle_sha256,
        occupied=set(existing_asset_ids),
    )
    run_id_map = _mapping(
        source_run_ids,
        kind="run",
        target_world_id=target_world_id,
        source_world_id="",
        bundle_sha256=bundle_sha256,
        occupied=set(existing_run_ids),
    )
    replacements = {
        source_world_id: target_world_id,
        **map_id_map,
        **scenario_id_map,
        **asset_id_map,
        **run_id_map,
    }

    blueprints: list[dict[str, Any]] = []
    blueprint_hashes: dict[tuple[str, int], tuple[str, str]] = {}
    for row in payload.map_blueprints:
        source_map_id = str(row.get("map_id") or "")
        revision = int(row.get("blueprint_revision") or 0)
        raw = replace_identifiers(dict(row.get("document") or {}), replacements)
        raw["map_id"] = map_id_map.get(source_map_id, source_map_id)
        document = MapBlueprintDocument.model_validate(raw)
        content_hash = canonical_content_hash(document)
        semantic_hash = canonical_content_hash(document.semantic_interface())
        blueprint_hashes[(document.map_id, revision)] = (content_hash, semantic_hash)
        blueprints.append(
            {
                **replace_identifiers(dict(row), replacements),
                "map_id": document.map_id,
                "blueprint_revision": revision,
                "document": document.model_dump(mode="json"),
                "content_hash": content_hash,
                "semantic_interface_hash": semantic_hash,
                "findings": [],
                "status": "ready",
            }
        )

    world_revisions: list[dict[str, Any]] = []
    world_revision_models: dict[int, WorldRevisionDocument] = {}
    for row in payload.world_revisions:
        revision = int(row.get("revision") or 0)
        raw = replace_identifiers(dict(row.get("document") or {}), replacements)
        raw["world_id"] = target_world_id
        raw["revision"] = revision
        requirements = []
        for requirement in list(raw.get("blueprint_requirements") or []):
            item = dict(requirement)
            key = (str(item.get("map_id") or ""), int(item.get("blueprint_revision") or 0))
            hashes = blueprint_hashes.get(key)
            if hashes:
                item["blueprint_hash"], item["semantic_interface_hash"] = hashes
            requirements.append(item)
        raw["blueprint_requirements"] = requirements
        raw["content_hash"] = ""
        document = _with_hash(WorldRevisionDocument.model_validate(raw), "content_hash")
        world_revision_models[revision] = document
        world_revisions.append(
            {
                **replace_identifiers(dict(row), replacements),
                "revision": revision,
                "document": document.model_dump(mode="json"),
                "content_hash": document.content_hash,
            }
        )

    map_definitions: list[dict[str, Any]] = []
    definition_models: dict[tuple[str, int], GridMapDefinition] = {}
    for row in payload.map_definitions:
        source_map_id = str(row.get("map_id") or "")
        definition_revision = int(row.get("definition_revision") or 0)
        raw = replace_identifiers(dict(row.get("document") or {}), replacements)
        raw.update(
            {
                "map_id": map_id_map.get(source_map_id, source_map_id),
                "world_id": target_world_id,
                "definition_revision": definition_revision,
                "world_revision": int(row.get("world_revision") or 0),
                "definition_hash": "",
                "semantic_interface_hash": "",
            }
        )
        definition = with_grid_definition_hashes(GridMapDefinition.model_validate(raw))
        definition_models[(definition.map_id, definition.definition_revision)] = definition
        map_definitions.append(
            {
                **replace_identifiers(dict(row), replacements),
                "map_id": definition.map_id,
                "definition_revision": definition.definition_revision,
                "world_revision": definition.world_revision,
                "document": definition.model_dump(mode="json"),
                "definition_hash": definition.definition_hash,
                "semantic_interface_hash": definition.semantic_interface_hash,
            }
        )

    releases: list[dict[str, Any]] = []
    release_models: dict[tuple[int, int], WorldReleaseDocument] = {}
    for row in payload.world_releases:
        world_revision = int(row.get("world_revision") or 0)
        release_number = int(row.get("release") or 0)
        revision_document = world_revision_models[world_revision]
        raw = replace_identifiers(dict(row.get("document") or {}), replacements)
        raw.update(
            {
                "world_id": target_world_id,
                "world_revision": world_revision,
                "release": release_number,
                "world_revision_hash": revision_document.content_hash,
                "release_hash": "",
            }
        )
        bindings = []
        for binding in list(raw.get("map_bindings") or []):
            item = dict(binding)
            definition = definition_models.get(
                (str(item.get("map_id") or ""), int(item.get("definition_revision") or 0))
            )
            if definition is None:
                raise ValueError(
                    "world_bundle_release_definition_missing:"
                    f"{item.get('map_id')}:{item.get('definition_revision')}"
                )
            item["definition_hash"] = definition.definition_hash
            item["semantic_interface_hash"] = definition.semantic_interface_hash
            bindings.append(item)
        raw["map_bindings"] = bindings
        release = certify_world_release(
            revision_document,
            WorldReleaseDocument.model_validate(raw),
            {
                definition.map_id: definition
                for definition in definition_models.values()
                if definition.world_revision == world_revision
            },
        )
        release_models[(world_revision, release_number)] = release
        releases.append(
            {
                **replace_identifiers(dict(row), replacements),
                "world_revision": world_revision,
                "release": release_number,
                "document": release.model_dump(mode="json"),
                "release_hash": release.release_hash,
            }
        )

    scenarios = tuple(
        {
            **replace_identifiers(dict(row), replacements),
            "id": scenario_id_map.get(str(row.get("id") or ""), str(row.get("id") or "")),
            "metadata": _import_metadata(
                replace_identifiers(dict(row.get("metadata") or {}), replacements),
                source_world_id=source_world_id,
                target_world_id=target_world_id,
                bundle_sha256=bundle_sha256,
            ),
        }
        for row in payload.scenarios
    )
    scenario_revisions = []
    for row in payload.scenario_revisions:
        revision = int(row.get("revision") or 0)
        source_scenario_id = str(row.get("scenario_id") or "")
        world_revision = int(row.get("world_revision") or 0)
        raw = replace_identifiers(dict(row.get("document") or {}), replacements)
        raw.update(
            {
                "scenario_id": scenario_id_map.get(source_scenario_id, source_scenario_id),
                "revision": revision,
                "world_id": target_world_id,
                "world_revision": world_revision,
                "world_revision_hash": world_revision_models[world_revision].content_hash,
                "content_hash": "",
            }
        )
        document = _with_hash(ScenarioRevisionDocument.model_validate(raw), "content_hash")
        scenario_revisions.append(
            {
                **replace_identifiers(dict(row), replacements),
                "scenario_id": document.scenario_id,
                "revision": revision,
                "world_revision": world_revision,
                "document": document.model_dump(mode="json"),
                "content_hash": document.content_hash,
            }
        )

    topics = tuple(
        _transform_topic(
            row,
            replacements,
            source_world_id=source_world_id,
            target_world_id=target_world_id,
            bundle_sha256=bundle_sha256,
        )
        for row in payload.topics
    )
    topic_history = tuple(
        _transform_topic(
            row,
            replacements,
            source_world_id=source_world_id,
            target_world_id=target_world_id,
            bundle_sha256=bundle_sha256,
        )
        for row in payload.topic_history
    )
    generation_runs = tuple(
        _transform_run(
            row,
            replacements,
            run_id_map,
            source_world_id=source_world_id,
            target_world_id=target_world_id,
            bundle_sha256=bundle_sha256,
        )
        for row in payload.generation_runs
    )
    world = replace_identifiers(dict(payload.world), replacements)
    world["id"] = target_world_id
    world["metadata"] = _import_metadata(
        replace_identifiers(dict(payload.world.get("metadata") or {}), replacements),
        source_world_id=source_world_id,
        target_world_id=target_world_id,
        bundle_sha256=bundle_sha256,
    )

    return TransformedWorldBundle(
        payload=WorldBundlePayload(
            world=world,
            topics=topics,
            topic_history=topic_history,
            generation_runs=generation_runs,
            map_blueprints=tuple(blueprints),
            world_revisions=tuple(world_revisions),
            map_definitions=tuple(map_definitions),
            world_releases=tuple(releases),
            scenarios=scenarios,
            scenario_revisions=tuple(scenario_revisions),
        ),
        identifier_map=replacements,
        asset_id_map=asset_id_map,
        run_id_map=run_id_map,
    )


def _referenced_assets(value: Any) -> set[str]:
    from .world_bundle import discover_image_asset_ids

    return discover_image_asset_ids(value)


def _transform_topic(
    row: Mapping[str, Any],
    replacements: Mapping[str, str],
    *,
    source_world_id: str,
    target_world_id: str,
    bundle_sha256: str,
) -> dict[str, Any]:
    result = replace_identifiers(dict(row), replacements)
    content = dict(result.get("content") or {})
    directives = dict(result.get("directives") or {})
    result["content_hash"] = canonical_hash(content)
    result["input_hash"] = canonical_hash(
        {
            "topic_id": str(result.get("topic_id") or ""),
            "content": content,
            "directives": directives,
        }
    )
    result["provenance"] = _import_metadata(
        dict(result.get("provenance") or {}),
        source_world_id=source_world_id,
        target_world_id=target_world_id,
        bundle_sha256=bundle_sha256,
    )
    return result


def _transform_run(
    row: Mapping[str, Any],
    replacements: Mapping[str, str],
    run_id_map: Mapping[str, str],
    *,
    source_world_id: str,
    target_world_id: str,
    bundle_sha256: str,
) -> dict[str, Any]:
    result = replace_identifiers(dict(row), replacements)
    source_run_id = str(row.get("run_id") or "")
    result["run_id"] = run_id_map.get(source_run_id, source_run_id)
    parent = row.get("parent_run_id")
    result["parent_run_id"] = run_id_map.get(str(parent), str(parent)) if parent else None
    if str(result.get("status") or "") in {"planned", "running"}:
        result["status"] = "canceled"
        result["completed_at"] = result.get("updated_at") or result.get("created_at")
    lineage = dict(result.get("lineage") or {})
    lineage["world_bundle_import"] = {
        "source_world_id": source_world_id,
        "target_world_id": target_world_id,
        "bundle_sha256": bundle_sha256,
        "execution_jobs_restored": False,
    }
    result["lineage"] = lineage
    return result
