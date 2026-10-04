from __future__ import annotations

import pytest

from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.session.genesis.world_forge_profile_deterministic import generate_deterministic_profile_topic
from app.rpg.session.genesis.world_forge_profile_generation import default_profile_registry
from app.rpg.session.genesis.world_forge_profile_graph import build_profile_launch_topic_graph, build_profile_topic_graph
from app.rpg.worlds import generation_compilation
from app.rpg.worlds.generation_publication_transaction import publication_transaction_report
from app.rpg.worlds.generation_starting_market import (
    StartingMarketCompilationError,
    require_valid_starting_market,
    starting_market_report,
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
            {"topic_id": "places", "metadata": {"field_definitions": []}},
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
            {"topic_id": "equipment_vehicles", "metadata": {"field_definitions": []}},
        ],
    }


def _rows() -> list[dict]:
    return [
        _topic("places", [
            {"id": "ent:place:1", "name": "Copper Market"},
            {"id": "ent:place:2", "name": "North Gate"},
        ]),
        _topic("equipment_vehicles", [
            {"id": "ent:item:1", "name": "Field Ration"},
            {"id": "ent:item:2", "name": "Lamp Cell"},
            {"id": "ent:item:3", "name": "Repair Kit"},
        ]),
        _topic("actors", [
            {
                "id": "ent:actor:1",
                "location_id": "ent:place:1",
                "vendor_inventory_item_ids": ["ent:item:1", "ent:item:2"],
            },
            {
                "id": "ent:actor:2",
                "location_id": "ent:place:2",
                "vendor_inventory_item_ids": ["ent:item:3"],
            },
        ]),
    ]


def test_profile_graph_adds_vendor_inventory_and_launch_dependency() -> None:
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    graph = build_profile_topic_graph(profile, campaign_template="classic_fantasy")
    actors = graph.node_map()["actors"]
    fields = {str(row.get("field_id")): row for row in actors.metadata["field_definitions"]}

    assert fields["vendor_inventory_item_ids"]["allowed_target_domains"] == ["equipment_vehicles"]
    assert "equipment_vehicles" in actors.dependencies

    launch = build_profile_launch_topic_graph(graph, profile)
    assert "equipment_vehicles" in launch.node_map()


def test_deterministic_actor_inventory_materializes_playable_starting_market() -> None:
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    graph = build_profile_topic_graph(
        profile,
        campaign_template="classic_fantasy",
        starting_location="ent:place:1",
    )
    node = graph.node_map()["actors"]
    places = tuple({"id": f"ent:place:{index}"} for index in range(1, 7))
    equipment = tuple({"id": f"ent:item:{index}"} for index in range(1, 7))
    dependencies = {
        domain_id: GeneratedTopic(
            topic_id=domain_id,
            entities=(
                places if domain_id == "places"
                else equipment if domain_id == "equipment_vehicles"
                else tuple({"id": f"ent:{domain_id}:{index}"} for index in range(1, 7))
            ),
        )
        for domain_id in node.dependencies
    }
    actors = generate_deterministic_profile_topic(
        node,
        campaign_context={"world_brief": {"title": "Cinder March"}},
        dependency_topics=dependencies,
    )
    rows = [
        _topic("places", list(places)),
        _topic("equipment_vehicles", list(equipment)),
        {"topic_id": "actors", "candidate": actors.as_dict()},
    ]

    report = starting_market_report(rows, graph.as_dict())

    assert report["passed"] is True
    materialization = report["materialization"]
    assert materialization["place_id"] == "ent:place:1"
    assert materialization["vendor_count"] >= 1
    assert materialization["inventory_item_count"] >= 1
    assert all(
        item["price"] > 0 and item["quantity"] > 0
        for vendor in materialization["vendors"]
        for item in vendor["inventory"]
    )


def test_starting_market_materialization_is_deterministic_and_bounded() -> None:
    first = starting_market_report(_rows(), _graph())
    second = starting_market_report(_rows(), _graph())

    assert first == second
    assert first["passed"] is True
    assert first["materialization"]["vendor_count"] <= 2
    assert first["materialization"]["inventory_item_count"] <= 10


def test_missing_vendor_and_invalid_inventory_are_blocking() -> None:
    rows = _rows()
    rows[-1]["candidate"]["entities"][0]["location_id"] = "ent:place:2"
    missing = starting_market_report(rows, _graph())
    rows = _rows()
    rows[-1]["candidate"]["entities"][0]["vendor_inventory_item_ids"] = ["ent:item:missing"]
    invalid = starting_market_report(rows, _graph())

    assert missing["passed"] is False
    assert any(row["code"] == "starting_vendor_required" for row in missing["issues"])
    assert invalid["passed"] is False
    assert any(row["code"] == "starting_vendor_inventory_reference_invalid" for row in invalid["issues"])


def test_unknown_starting_place_is_blocking() -> None:
    graph = _graph()
    graph["metadata"]["starting_location"] = "ent:place:missing"
    report = starting_market_report(_rows(), graph)

    assert report["passed"] is False
    assert any(row["code"] == "starting_market_place_unresolved" for row in report["issues"])


def test_certified_compilation_fails_before_legacy_compiler(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _rows()
    rows[-1]["candidate"]["entities"][0]["vendor_inventory_item_ids"] = []
    called = False

    def legacy(**_kwargs: object) -> object:
        nonlocal called
        called = True
        raise AssertionError("legacy compiler should not run")

    monkeypatch.setattr(generation_compilation, "compile_world_generation_publication", legacy)
    monkeypatch.setattr(generation_compilation, "_reports", lambda values, graph: {"starting_market": starting_market_report(values, graph)})
    monkeypatch.setattr(generation_compilation, "_graph_audits", lambda: (("starting_market", starting_market_report, require_valid_starting_market),))
    monkeypatch.setattr(generation_compilation, "require_unique_canon_identifiers", lambda _rows: None)
    monkeypatch.setattr(generation_compilation, "require_resolved_objective_named_claims", lambda _rows: None)

    with pytest.raises(StartingMarketCompilationError):
        generation_compilation.compile_world_generation_artifact(
            mode="certified_release",
            run={"graph": _graph()},
            world={},
            topic_rows=rows,
            revision=1,
        )
    assert called is False


def test_transaction_discovers_failed_starting_market_report() -> None:
    report = publication_transaction_report(
        {"run_id": "run:1", "world_id": "world:1", "status": "review", "progress": {}},
        {"launch_ready": False, "missing_requirements": ["starting_market"], "starting_market": {"passed": False, "issues": []}},
    )

    assert report["publishable"] is False
    assert "starting_market" in report["failed_reports"]
