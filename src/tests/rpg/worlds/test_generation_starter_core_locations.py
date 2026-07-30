from __future__ import annotations

import pytest

from app.rpg.worlds import generation_compilation, generation_starter_core_locations
from app.rpg.worlds.generation_starter_core_locations import (
    StarterCoreLocationCompilationError,
    require_valid_starter_core_locations,
    starter_core_location_report,
)


def _topic(topic_id: str, entities: list[dict]) -> dict:
    return {
        "topic_id": topic_id,
        "candidate": {
            "topic_id": topic_id,
            "documents": [],
            "entities": entities,
            "facts": [],
            "relationships": [],
            "knowledge_rules": [],
            "story_threads": [],
            "provenance": {},
        },
    }


def _graph() -> dict:
    return {
        "metadata": {"starting_location": "ent:place:1"},
        "nodes": [
            {"topic_id": "places", "metadata": {"field_definitions": [{"field_id": "connected_place_ids"}]}},
            {"topic_id": "actors", "metadata": {"field_definitions": [{"field_id": "vendor_inventory_item_ids"}]}},
        ],
    }


def _rows() -> list[dict]:
    return [
        _topic("regions", [{"id": "ent:region:1", "name": "Cinder March"}]),
        _topic("places", [
            {
                "id": "ent:place:1",
                "name": "Copper Market",
                "region_id": "ent:region:1",
                "connected_place_ids": ["ent:place:2"],
            },
            {
                "id": "ent:place:2",
                "name": "North Gate",
                "region_id": "ent:region:1",
                "connected_place_ids": ["ent:place:1"],
            },
        ]),
    ]


def test_starter_settlement_and_interior_are_navigable_and_reciprocal() -> None:
    report = starter_core_location_report(_rows(), _graph())

    assert report["passed"] is True
    materialization = report["materialization"]
    settlement = materialization["settlement_slot"]
    interior = materialization["interior_slot"]
    assert settlement["location_id"] == "ent:place:1"
    assert settlement["map_level"] == "settlement"
    assert interior["map_level"] == "interior"
    assert settlement["simulation_readiness"] == "navigable"
    assert interior["simulation_readiness"] == "navigable"
    assert len(materialization["map_definitions"]) == 2
    by_location = {row["metadata"]["location_id"]: row for row in materialization["map_definitions"]}
    settlement_map = by_location[settlement["location_id"]]
    interior_map = by_location[interior["location_id"]]
    assert settlement_map["definition_hash"].startswith("sha256:")
    assert interior_map["semantic_interface_hash"].startswith("sha256:")
    assert interior_map["map_id"] in {row["target"]["map_id"] for row in settlement_map["portals"]}
    assert settlement_map["map_id"] in {row["target"]["map_id"] for row in interior_map["portals"]}


def test_missing_neighbor_prevents_core_materialization() -> None:
    rows = _rows()
    rows[1]["candidate"]["entities"][0]["connected_place_ids"] = []

    report = starter_core_location_report(rows, _graph())

    assert report["passed"] is False
    assert any(row["code"] == "starter_core_plan_unavailable" for row in report["issues"])


def test_missing_interior_definition_is_blocking(monkeypatch: pytest.MonkeyPatch) -> None:
    original = generation_starter_core_locations.build_starter_map_definitions

    def incomplete(*args: object, **kwargs: object) -> tuple[object, ...]:
        definitions = original(*args, **kwargs)
        return tuple(
            definition
            for definition in definitions
            if definition.metadata.get("starter_role") != "interior"
        )

    monkeypatch.setattr(generation_starter_core_locations, "build_starter_map_definitions", incomplete)
    report = starter_core_location_report(_rows(), _graph())

    assert report["passed"] is False
    assert any(row["code"] == "starter_core_map_definition_missing" for row in report["issues"])


def test_emitted_map_level_role_and_hash_corruption_is_blocking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = generation_starter_core_locations.build_starter_map_definitions

    def corrupted(*args: object, **kwargs: object) -> tuple[object, ...]:
        definitions = list(original(*args, **kwargs))
        for index, definition in enumerate(definitions):
            if definition.metadata.get("starter_role") == "settlement":
                definitions[index] = definition.model_copy(
                    update={
                        "level": "interior",
                        "metadata": {
                            **dict(definition.metadata),
                            "starter_role": "interior",
                        },
                    }
                )
                break
        return tuple(definitions)

    monkeypatch.setattr(generation_starter_core_locations, "build_starter_map_definitions", corrupted)
    report = starter_core_location_report(_rows(), _graph())
    codes = {row["code"] for row in report["issues"]}

    assert report["passed"] is False
    assert "starter_core_map_binding_invalid" in codes
    assert "starter_core_map_hash_invalid" in codes


def test_legacy_graph_without_release6_contract_is_skipped() -> None:
    graph = {"metadata": {}, "nodes": [{"topic_id": "places", "metadata": {"field_definitions": []}}]}

    report = starter_core_location_report([], graph)
    require_valid_starter_core_locations([], graph)

    assert report["passed"] is True
    assert report["checks"]["contract_enabled"] is False


def test_certified_compilation_fails_before_legacy_compiler(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _rows()
    rows[1]["candidate"]["entities"][0]["connected_place_ids"] = []
    called = False

    def legacy(**_kwargs: object) -> object:
        nonlocal called
        called = True
        raise AssertionError("legacy compiler should not run")

    monkeypatch.setattr(generation_compilation, "compile_world_generation_publication", legacy)
    monkeypatch.setattr(generation_compilation, "_reports", lambda values, graph: {"starter_core_locations": starter_core_location_report(values, graph)})
    monkeypatch.setattr(generation_compilation, "_graph_audits", lambda: (("starter_core_locations", starter_core_location_report, require_valid_starter_core_locations),))
    monkeypatch.setattr(generation_compilation, "require_unique_canon_identifiers", lambda _rows: None)
    monkeypatch.setattr(generation_compilation, "require_resolved_objective_named_claims", lambda _rows: None)

    with pytest.raises(StarterCoreLocationCompilationError):
        generation_compilation.compile_world_generation_artifact(
            mode="certified_release",
            run={"graph": _graph()},
            world={},
            topic_rows=rows,
            revision=1,
        )
    assert called is False
