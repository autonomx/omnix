from __future__ import annotations

import pytest

from app.rpg.worlds import generation_compilation, generation_starter_neighbor
from app.rpg.worlds.generation_starter_neighbor import (
    StarterNeighborCompilationError,
    require_valid_starter_neighbor,
    starter_neighbor_report,
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


def test_neighbor_is_navigable_and_frontier_is_deferred() -> None:
    report = starter_neighbor_report(_rows(), _graph())

    assert report["passed"] is True
    materialization = report["materialization"]
    neighbor = materialization["neighbor_slot"]
    definition = materialization["neighbor_map_definition"]
    assert materialization["canonical_neighbor_id"] == "ent:place:2"
    assert neighbor["location_id"] == "ent:place:2"
    assert neighbor["simulation_readiness"] == "navigable"
    assert definition["metadata"]["starter_role"] == "neighbor"
    assert definition["definition_hash"].startswith("sha256:")
    assert len(materialization["deferred_slots"]) == 1
    assert materialization["deferred_slots"][0]["deferred"] is True
    assert materialization["deferred_slots"][0]["metadata"]["materialize_on_approach"] is True
    assert len(materialization["predictive_queue"]) == 1
    assert materialization["predictive_queue"][0]["fallback"] == "navigable_placeholder"
    assert materialization["predictive_queue"][0]["presentation_optional"] is True


def test_missing_canonical_neighbor_blocks_materialization() -> None:
    rows = _rows()
    rows[1]["candidate"]["entities"][0]["connected_place_ids"] = []

    report = starter_neighbor_report(rows, _graph())

    assert report["passed"] is False
    assert any(row["code"] == "starter_neighbor_plan_unavailable" for row in report["issues"])


def test_missing_predictive_frontier_job_is_blocking(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(generation_starter_neighbor, "predictive_materialization_queue", lambda *_args, **_kwargs: ())

    report = starter_neighbor_report(_rows(), _graph())

    assert report["passed"] is False
    assert any(row["code"] == "starter_frontier_predictive_job_missing" for row in report["issues"])


def test_legacy_graph_without_release6_contract_is_skipped() -> None:
    graph = {"metadata": {}, "nodes": [{"topic_id": "places", "metadata": {"field_definitions": []}}]}

    report = starter_neighbor_report([], graph)
    require_valid_starter_neighbor([], graph)

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
    monkeypatch.setattr(generation_compilation, "_reports", lambda values, graph: {"starter_neighbor": starter_neighbor_report(values, graph)})
    monkeypatch.setattr(generation_compilation, "_graph_audits", lambda: (("starter_neighbor", starter_neighbor_report, require_valid_starter_neighbor),))
    monkeypatch.setattr(generation_compilation, "require_unique_canon_identifiers", lambda _rows: None)
    monkeypatch.setattr(generation_compilation, "require_resolved_objective_named_claims", lambda _rows: None)

    with pytest.raises(StarterNeighborCompilationError):
        generation_compilation.compile_world_generation_artifact(
            mode="certified_release",
            run={"graph": _graph()},
            world={},
            topic_rows=rows,
            revision=1,
        )
    assert called is False
