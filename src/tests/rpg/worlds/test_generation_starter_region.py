from __future__ import annotations

import pytest

from app.rpg.worlds import generation_compilation
from app.rpg.worlds.generation_starter_region import (
    StarterRegionCompilationError,
    require_valid_starter_region,
    starter_region_issues,
    starter_region_report,
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
            {
                "topic_id": "places",
                "metadata": {"field_definitions": [{"field_id": "connected_place_ids"}]},
            },
            {
                "topic_id": "actors",
                "metadata": {"field_definitions": [{"field_id": "vendor_inventory_item_ids"}]},
            },
        ],
    }


def _rows() -> list[dict]:
    return [
        _topic("regions", [{"id": "ent:region:1", "name": "Cinder March"}]),
        _topic(
            "places",
            [
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
            ],
        ),
    ]


def test_starter_region_uses_canonical_region_identity() -> None:
    report = starter_region_report(_rows(), _graph())

    assert report["passed"] is True
    materialization = report["materialization"]
    assert materialization["canonical_region_id"] == "ent:region:1"
    assert materialization["region_slot"]["location_id"] == "ent:region:1"
    assert materialization["region_slot"]["metadata"]["owns_world_graph"] is True
    assert materialization["region_slot"]["metadata"]["canonical_region"] is True


def test_missing_and_unknown_region_references_are_blocking() -> None:
    rows = _rows()
    rows[1]["candidate"]["entities"][0].pop("region_id")
    missing = starter_region_issues(rows, _graph())
    rows = _rows()
    rows[1]["candidate"]["entities"][0]["region_id"] = "ent:region:missing"
    unknown = starter_region_issues(rows, _graph())

    assert any(row.code == "starter_region_reference_unresolved" for row in missing)
    assert any(row.code == "starter_region_reference_unresolved" for row in unknown)


def test_legacy_graph_without_release6_contract_is_skipped() -> None:
    graph = {"metadata": {}, "nodes": [{"topic_id": "regions", "metadata": {"field_definitions": []}}]}

    report = starter_region_report([], graph)
    require_valid_starter_region([], graph)

    assert report["passed"] is True
    assert report["checks"]["contract_enabled"] is False


def test_certified_compilation_fails_before_legacy_compiler(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _rows()
    rows[1]["candidate"]["entities"][0]["region_id"] = "ent:region:missing"
    called = False

    def legacy(**_kwargs: object) -> object:
        nonlocal called
        called = True
        raise AssertionError("legacy compiler should not run")

    monkeypatch.setattr(generation_compilation, "compile_world_generation_publication", legacy)
    monkeypatch.setattr(generation_compilation, "_reports", lambda values, graph: {"starter_region": starter_region_report(values, graph)})
    monkeypatch.setattr(generation_compilation, "_graph_audits", lambda: (("starter_region", starter_region_report, require_valid_starter_region),))
    monkeypatch.setattr(generation_compilation, "require_unique_canon_identifiers", lambda _rows: None)
    monkeypatch.setattr(generation_compilation, "require_resolved_objective_named_claims", lambda _rows: None)

    with pytest.raises(StarterRegionCompilationError):
        generation_compilation.compile_world_generation_artifact(
            mode="certified_release",
            run={"graph": _graph()},
            world={},
            topic_rows=rows,
            revision=1,
        )
    assert called is False
