from __future__ import annotations

import pytest

from app.rpg.worlds import generation_compilation
from app.rpg.worlds.generation_publication_transaction import publication_transaction_report
from app.rpg.worlds.generation_starter_topology import (
    StarterTopologyCompilationError,
    require_valid_starter_topology,
    starter_topology_issues,
    starter_topology_report,
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


def _graph(starting_location: str = "ent:place:1") -> dict:
    return {
        "metadata": {"starting_location": starting_location},
        "nodes": [
            {
                "topic_id": "places",
                "metadata": {
                    "field_definitions": [
                        {
                            "field_id": "connected_place_ids",
                            "value_type": "entity_ref_list",
                            "allowed_target_domains": ["places"],
                        }
                    ]
                },
            },
            {
                "topic_id": "actors",
                "metadata": {
                    "field_definitions": [
                        {
                            "field_id": "vendor_inventory_item_ids",
                            "value_type": "entity_ref_list",
                            "allowed_target_domains": ["equipment_vehicles"],
                        }
                    ]
                },
            },
        ],
    }


def _rows() -> list[dict]:
    return [
        _topic(
            "places",
            [
                {
                    "id": "ent:place:1",
                    "name": "Copper Market",
                    "connected_place_ids": ["ent:place:2"],
                },
                {
                    "id": "ent:place:2",
                    "name": "North Gate",
                    "connected_place_ids": ["ent:place:1", "ent:place:3"],
                },
                {
                    "id": "ent:place:3",
                    "name": "Ash Road",
                    "connected_place_ids": ["ent:place:2"],
                },
            ],
        )
    ]


def test_starter_topology_derives_connected_canonical_plan() -> None:
    report = starter_topology_report(_rows(), _graph())

    assert report["passed"] is True
    plan = report["materialization"]
    assert plan["starting_location_id"] == "ent:place:1"
    slots = {row["role"]: row for row in plan["slots"]}
    assert slots["settlement"]["location_id"] == "ent:place:1"
    assert slots["neighbor"]["location_id"] == "ent:place:2"
    assert len(plan["topology"]["locations"]) == 5
    assert len(plan["topology"]["routes"]) == 3


def test_unknown_start_and_missing_connected_neighbor_are_blocking() -> None:
    unknown = starter_topology_issues(_rows(), _graph("ent:place:missing"))
    rows = _rows()
    rows[0]["candidate"]["entities"][0]["connected_place_ids"] = []
    missing_neighbor = starter_topology_issues(rows, _graph())

    assert any(row.code == "starter_topology_starting_place_unresolved" for row in unknown)
    assert any(row.code == "starter_topology_neighbor_unresolved" for row in missing_neighbor)


def test_legacy_graph_without_release6_contract_is_skipped() -> None:
    graph = {"metadata": {}, "nodes": [{"topic_id": "places", "metadata": {"field_definitions": []}}]}

    report = starter_topology_report([], graph)
    require_valid_starter_topology([], graph)

    assert report["passed"] is True
    assert report["checks"]["contract_enabled"] is False
    assert report["issues"] == []


def test_certified_compilation_fails_before_legacy_compiler(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _rows()
    rows[0]["candidate"]["entities"][0]["connected_place_ids"] = []
    called = False

    def legacy(**_kwargs: object) -> object:
        nonlocal called
        called = True
        raise AssertionError("legacy compiler should not run")

    monkeypatch.setattr(generation_compilation, "compile_world_generation_publication", legacy)
    monkeypatch.setattr(generation_compilation, "_reports", lambda values, graph: {"starter_topology": starter_topology_report(values, graph)})
    monkeypatch.setattr(generation_compilation, "_graph_audits", lambda: (("starter_topology", starter_topology_report, require_valid_starter_topology),))
    monkeypatch.setattr(generation_compilation, "require_unique_canon_identifiers", lambda _rows: None)
    monkeypatch.setattr(generation_compilation, "require_resolved_objective_named_claims", lambda _rows: None)

    with pytest.raises(StarterTopologyCompilationError):
        generation_compilation.compile_world_generation_artifact(
            mode="certified_release",
            run={"graph": _graph()},
            world={},
            topic_rows=rows,
            revision=1,
        )
    assert called is False


def test_transaction_discovers_failed_starter_topology_report() -> None:
    report = publication_transaction_report(
        {"run_id": "run:1", "world_id": "world:1", "status": "review", "progress": {}},
        {"launch_ready": False, "missing_requirements": ["starter_topology"], "starter_topology": {"passed": False, "issues": []}},
    )

    assert report["publishable"] is False
    assert "starter_topology" in report["failed_reports"]
