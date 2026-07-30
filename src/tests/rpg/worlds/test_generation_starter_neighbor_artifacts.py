from __future__ import annotations

import pytest

from app.rpg.worlds import generation_starter_neighbor_artifacts
from app.rpg.worlds.generation_starter_neighbor_artifacts import (
    StarterNeighborArtifactCompilationError,
    require_valid_starter_neighbor_artifacts,
    starter_neighbor_artifact_report,
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
                "metadata": {
                    "field_definitions": [{"field_id": "connected_place_ids"}]
                },
            },
            {
                "topic_id": "actors",
                "metadata": {
                    "field_definitions": [{"field_id": "vendor_inventory_item_ids"}]
                },
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


def test_neighbor_artifacts_are_exact_and_frontier_queue_is_bounded() -> None:
    report = starter_neighbor_artifact_report(_rows(), _graph())

    assert report["passed"] is True
    materialization = report["materialization"]
    assert materialization["neighbor_map_id"].endswith(":neighbor")
    assert len(materialization["deferred_location_ids"]) == 1
    assert len(materialization["predictive_queue"]) == 1
    assert materialization["predictive_queue"][0]["resource_class"] == "cpu"
    assert materialization["predictive_queue"][0]["fallback"] == "navigable_placeholder"


def test_corrupt_neighbor_definition_hash_and_binding_are_blocking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = generation_starter_neighbor_artifacts.build_starter_map_definitions

    def corrupted(*args: object, **kwargs: object) -> tuple[object, ...]:
        definitions = list(original(*args, **kwargs))
        for index, definition in enumerate(definitions):
            if definition.metadata.get("starter_role") == "neighbor":
                definitions[index] = definition.model_copy(
                    update={"map_id": "map:drifted:neighbor", "level": "interior"}
                )
                break
        return tuple(definitions)

    monkeypatch.setattr(
        generation_starter_neighbor_artifacts,
        "build_starter_map_definitions",
        corrupted,
    )
    report = starter_neighbor_artifact_report(_rows(), _graph())
    codes = {row["code"] for row in report["issues"]}

    assert report["passed"] is False
    assert "starter_neighbor_artifact_binding_invalid" in codes
    assert "starter_neighbor_artifact_hash_invalid" in codes
    with pytest.raises(StarterNeighborArtifactCompilationError):
        require_valid_starter_neighbor_artifacts(_rows(), _graph())


def test_frontier_cannot_materialize_in_launch_definitions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = generation_starter_neighbor_artifacts.build_starter_map_definitions

    def eager(plan: object, **kwargs: object) -> tuple[object, ...]:
        return original(plan, include_deferred=True, **kwargs)

    monkeypatch.setattr(
        generation_starter_neighbor_artifacts,
        "build_starter_map_definitions",
        eager,
    )
    report = starter_neighbor_artifact_report(_rows(), _graph())

    assert report["passed"] is False
    assert any(
        row["code"] == "starter_frontier_artifact_materialized_early"
        for row in report["issues"]
    )


def test_duplicate_and_non_navigable_predictive_jobs_are_blocking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = generation_starter_neighbor_artifacts.predictive_materialization_queue

    def corrupted(*args: object, **kwargs: object) -> tuple[dict, ...]:
        queue = [dict(row) for row in original(*args, **kwargs)]
        duplicate = {**queue[0], "fallback": "presentation_required"}
        return tuple([*queue, duplicate])

    monkeypatch.setattr(
        generation_starter_neighbor_artifacts,
        "predictive_materialization_queue",
        corrupted,
    )
    report = starter_neighbor_artifact_report(_rows(), _graph())
    codes = {row["code"] for row in report["issues"]}

    assert report["passed"] is False
    assert "starter_frontier_artifact_queue_duplicate" in codes
    assert "starter_frontier_artifact_fallback_invalid" in codes


def test_legacy_graph_without_release6_contract_is_skipped() -> None:
    graph = {
        "metadata": {},
        "nodes": [
            {"topic_id": "places", "metadata": {"field_definitions": []}}
        ],
    }

    report = starter_neighbor_artifact_report([], graph)
    require_valid_starter_neighbor_artifacts([], graph)

    assert report["passed"] is True
    assert report["materialization"]["contract_enabled"] is False
