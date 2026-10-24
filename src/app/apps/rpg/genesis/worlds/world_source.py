"""A world written as readable source, compiled into an importable bundle (roadmap §4.4).

The starter world ships as ``world.source.json``: its places, people, economy, routines, knowledge, pressures,
bestiary, quests, maps and openings. ``build_bundle`` compiles it with the same compilers a published world goes
through (the world revision, its certified release, the map definitions it binds, one scenario per opening), and the
build is deterministic, so the bundle a workspace installs is a pure function of the source.
"""
from __future__ import annotations

from typing import Any

from app.apps.rpg.world.map_grid_contracts import GridMapDefinition, with_grid_definition_hashes

from .contracts import MapDefinitionBinding, MapInitializationOperation
from .semantic_validation import certify_world_release, validate_scenario_against_release
from .service import compile_scenario_revision, compile_world_release, compile_world_revision
from .world_bundle import WorldBundlePayload, build_world_bundle_archive


def _manifest(canon: dict[str, Any], topology: dict[str, Any], maps: list[dict[str, Any]]) -> dict[str, list[str]]:
    def ids(rows: Any) -> list[str]:
        return [str(row["id"]) for row in rows or () if isinstance(row, dict) and row.get("id")]

    return {
        "characters": ids(canon.get("characters")),
        "creatures": ids(canon.get("bestiary")),
        "items": ids(canon.get("items")),
        "locations": ids(topology.get("locations")),
        "maps": [str(row["map_id"]) for row in maps],
        "quests": ids(canon.get("quests")),
        "regions": ids(canon.get("regions")),
    }


def _definitions(source: dict[str, Any], world_id: str, revision: int) -> list[GridMapDefinition]:
    places = {row["id"]: row for row in source["revision"]["topology"]["locations"]}
    definitions = []
    for row in source["maps"]:
        rows = list(row["rows"])
        place = places[row["location_id"]]
        definition = GridMapDefinition.model_validate({
            "map_id": row["map_id"],
            "level": row["level"],
            "definition_revision": 1,
            "world_id": world_id,
            "world_revision": revision,
            "width": len(rows[0]),
            "height": len(rows),
            "terrain_palette": source["palette"],
            "terrain_rows": rows,
            "spawn_points": [{"spawn_point_id": spawn_id, "cell": cell, "tags": tags}
                             for spawn_id, cell, tags in row["spawns"]],
            "zones": [{"zone_id": zone_id, "name": name, "cells": cells} for zone_id, name, cells in row["zones"]],
            "portals": [{"portal_id": portal_id, "direction": "forward",
                         "source": {"map_id": row["map_id"], "cell": cell},
                         "target": {"map_id": target_map, "cell": target_cell}}
                        for portal_id, cell, target_map, target_cell in row["portals"]],
            "metadata": {"location_id": row["location_id"], "description": place["description"]},
        })
        definitions.append(with_grid_definition_hashes(definition))
    return definitions


def compile_world(source: dict[str, Any]) -> dict[str, Any]:
    """The bundle's records from a world's readable source: the world, its revision, map definitions, certified
    release and scenarios. Every record is dated ``released_at``, the source's own release date."""
    released = str(source["released_at"])
    world = {**source["world"], "created_at": released, "updated_at": released}
    authored = source["revision"]
    canon, topology = authored["canon"], authored["topology"]
    revision = compile_world_revision(
        world_id=world["id"],
        revision=1,
        title=authored["title"],
        canon=canon,
        entity_manifest=_manifest(canon, topology, source["maps"]),
        topology=topology,
        adventure_seeds=authored["adventure_seeds"],
        provenance=authored["provenance"],
    )
    definitions = _definitions(source, world["id"], revision.revision)
    by_map = {definition.map_id: definition for definition in definitions}
    bindings = [
        MapDefinitionBinding(
            map_id=definition.map_id,
            blueprint_revision=1,
            definition_revision=definition.definition_revision,
            definition_hash=definition.definition_hash,
            semantic_interface_hash=definition.semantic_interface_hash,
            simulation_readiness="certified",
            presentation_readiness="ready",
        )
        for definition in definitions
    ]
    content = _manifest(canon, topology, source["maps"])
    release = certify_world_release(
        revision,
        compile_world_release(
            revision,
            release=1,
            map_bindings=bindings,
            compiler_provenance={"compiler": "builtin_world_source_v1"},
            certification={
                "launch_ready": True,
                "missing_requirements": [],
                "content_summary": {key: len(content[key]) for key in ("characters", "quests", "maps", "locations")},
            },
        ),
        by_map,
    )
    if not release.certification.get("launch_ready"):
        raise ValueError(f"the world {world['id']} is not launch ready: {release.certification.get('missing_requirements')}")
    scenarios: list[dict[str, Any]] = []
    scenario_revisions = []
    for opening in source["scenarios"]:
        start_map = next(row["map_id"] for row in source["maps"] if row["location_id"] == opening["starting_location_id"])
        scenario = compile_scenario_revision(
            scenario_id=opening["scenario_id"],
            revision=1,
            world_revision=revision,
            starting_location_id=opening["starting_location_id"],
            compatible_release=release.release,
            starting_epoch=opening["starting_epoch"],
            initial_npc_ids=opening["initial_npc_ids"],
            starting_resources=source["starting_resources"],
            opening_seed_ids=opening["opening_seed_ids"],
            map_initialization=[
                MapInitializationOperation(operation_id=f"init:{npc_id.split(':', 1)[1]}:{start_map.rsplit(':', 1)[1]}",
                                           map_id=start_map, type="place_actor", target_id=npc_id,
                                           payload={"spawn_point_id": spawn_id})
                for npc_id, spawn_id in opening["place"]
            ],
        )
        validate_scenario_against_release(scenario, release, by_map)
        scenario_revisions.append(scenario)
        scenarios.append({
            "id": opening["scenario_id"], "title": opening["title"], "description": opening["description"],
            "status": "published", "created_at": released, "updated_at": released,
            "metadata": {**opening["metadata"], "starting_location_id": opening["starting_location_id"]},
        })
    return {
        "world": world,
        "world_revisions": [{"revision": revision.revision, "content_hash": revision.content_hash,
                             "created_at": released, "document": revision.model_dump(mode="json")}],
        "map_definitions": [{"map_id": definition.map_id, "definition_revision": definition.definition_revision,
                             "world_revision": definition.world_revision, "definition_hash": definition.definition_hash,
                             "semantic_interface_hash": definition.semantic_interface_hash,
                             "created_at": released, "document": definition.model_dump(mode="json")}
                            for definition in definitions],
        "world_releases": [{"release": release.release, "world_revision": release.world_revision,
                            "release_hash": release.release_hash, "created_at": released,
                            "document": release.model_dump(mode="json")}],
        "scenarios": scenarios,
        "scenario_revisions": [{"scenario_id": scenario.scenario_id, "revision": scenario.revision,
                                "world_revision": scenario.world_revision, "content_hash": scenario.content_hash,
                                "created_at": released, "document": scenario.model_dump(mode="json")}
                               for scenario in scenario_revisions],
    }


def build_bundle(source: dict[str, Any]) -> bytes:
    """The world's importable bundle, the same bytes every time for the same source."""
    payload = WorldBundlePayload.model_validate(compile_world(source))
    return build_world_bundle_archive(payload, (), exported_at=str(source["released_at"])).content


__all__ = ["build_bundle", "compile_world"]
