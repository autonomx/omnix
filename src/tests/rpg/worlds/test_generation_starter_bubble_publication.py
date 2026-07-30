from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.rpg.worlds.contracts import canonical_content_hash
from app.rpg.worlds.generation_publication import WorldGenerationPublication
from app.rpg.worlds.generation_starter_bubble_publication import (
    StarterBubblePublicationError,
    apply_certified_starter_bubble,
    persist_certified_starter_maps,
)
from app.rpg.worlds.service import compile_world_release, compile_world_revision
from app.rpg.worlds.starter_bubble import (
    build_starter_bubble,
    build_starter_map_definitions,
    starter_bubble_certification,
)


def _publication() -> WorldGenerationPublication:
    revision = compile_world_revision(
        world_id="world:cinder",
        revision=3,
        title="Cinder March",
        canon={"entities": {}},
        entity_manifest={"entities": {}, "manifest": {}},
        topology={
            "schema_version": "rpg_world_topology_v1",
            "locations": ["ent:place:1", "ent:place:2"],
            "routes": [],
        },
        provenance={
            "topic_hashes": {"places": "sha256:" + "a" * 64},
        },
    )
    release = compile_world_release(
        revision,
        release=1,
        indexes={"existing": True},
        certification={"launch_ready": True},
        artifact_stage="playtested",
    )
    return WorldGenerationPublication(
        world_revision=revision,
        world_release=release,
        certification={"launch_ready": True},
    )


def _certificate() -> dict:
    plan = build_starter_bubble(
        world_id="world:cinder",
        source_world_revision=3,
        starting_location_id="ent:place:1",
        neighboring_location_id="ent:place:2",
    )
    definitions = build_starter_map_definitions(
        plan,
        target_world_revision=3,
        definition_revisions={
            slot.map_id: 3
            for slot in plan.map_slots()
            if slot.map_id
        },
    )
    native = starter_bubble_certification(plan, definitions)
    payload = {
        "schema_version": "rpg_world_starter_bubble_release_v1",
        "contract_enabled": True,
        "skipped": False,
        "simulation_certified": True,
        "presentation_complete": False,
        "optional_art_blocks_gameplay": False,
        "plan": plan.model_dump(mode="json"),
        "map_definitions": [
            definition.model_dump(mode="json")
            for definition in definitions
        ],
        "native_certification": native,
        "component_statuses": {"starter_topology": True},
        "component_reports": {},
        "starting_market": {
            "place_id": "ent:place:1",
            "vendor_count": 1,
            "vendors": [{"vendor_id": "ent:actor:1", "inventory": []}],
        },
        "content_hash": "",
    }
    payload["content_hash"] = canonical_content_hash(payload)
    return payload


def test_certified_starter_bubble_is_bound_into_initial_release() -> None:
    bundle = apply_certified_starter_bubble(_publication(), _certificate())

    revision = bundle.publication.world_revision
    release = bundle.publication.world_release
    assert bundle.report["passed"] is True
    assert bundle.report["map_definition_count"] == 3
    assert len(bundle.map_definitions) == 3
    assert revision.topology["starter_bubble"]["region_id"]
    assert len(release.map_bindings) == 3
    assert all(binding.definition_revision == 3 for binding in release.map_bindings)
    assert all(binding.simulation_readiness == "navigable" for binding in release.map_bindings)
    assert release.indexes["starter_bubble"]["starting_location_id"] == "ent:place:1"
    assert release.indexes["starting_market"]["vendor_count"] == 1
    queue = release.indexes["predictive_materialization"]
    assert len(queue) == 1
    assert queue[0]["location_id"].endswith(":frontier")
    frontier_map_id = next(
        slot["map_id"]
        for slot in release.indexes["starter_bubble"]["slots"]
        if slot["role"] == "frontier"
    )
    assert frontier_map_id not in {definition.map_id for definition in bundle.map_definitions}
    assert frontier_map_id not in {binding.map_id for binding in release.map_bindings}
    assert release.certification["starter_bubble_publication"]["passed"] is True
    assert release.certification["optional_art_blocks_gameplay"] is False


def test_certificate_hash_and_revision_identity_are_fail_closed() -> None:
    bad_hash = _certificate()
    bad_hash["content_hash"] = "sha256:" + "0" * 64
    with pytest.raises(
        StarterBubblePublicationError,
        match="starter_bubble_certificate_hash_mismatch",
    ):
        apply_certified_starter_bubble(_publication(), bad_hash)

    wrong_revision = _certificate()
    wrong_revision["plan"]["source_world_revision"] = 4
    wrong_revision["content_hash"] = canonical_content_hash(
        {**wrong_revision, "content_hash": ""}
    )
    with pytest.raises(
        StarterBubblePublicationError,
        match="starter_bubble_revision_mismatch",
    ):
        apply_certified_starter_bubble(_publication(), wrong_revision)


def test_certified_map_definitions_are_persisted_exactly_once() -> None:
    bundle = apply_certified_starter_bubble(_publication(), _certificate())
    calls: list[dict] = []

    class _Maps:
        def put_definition(self, _context: object, **kwargs: object) -> dict:
            calls.append(dict(kwargs))
            return dict(kwargs)

    work = SimpleNamespace(map_instances=_Maps())
    stored = persist_certified_starter_maps(work, object(), bundle)

    assert len(stored) == 3
    assert len(calls) == 3
    assert {row["map_id"] for row in calls} == {
        definition.map_id for definition in bundle.map_definitions
    }
    assert all(row["world_revision"] == 3 for row in calls)
    assert all(str(row["definition_hash"]).startswith("sha256:") for row in calls)


def test_legacy_certificate_skip_keeps_release_unchanged() -> None:
    publication = _publication()

    bundle = apply_certified_starter_bubble(
        publication,
        {"contract_enabled": False},
    )

    assert bundle.publication is publication
    assert bundle.map_definitions == ()
    assert bundle.report["skipped"] is True
