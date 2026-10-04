from __future__ import annotations

import pytest

from app.rpg.worlds import generation_compilation, generation_starter_bubble_release
from app.rpg.worlds.contracts import canonical_content_hash
from app.rpg.worlds.generation_publication_transaction import publication_transaction_report
from app.rpg.worlds.generation_starter_bubble_release import (
    StarterBubbleReleaseCompilationError,
    require_valid_starter_bubble_release,
    starter_bubble_release_report,
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
        "metadata": {
            "starting_location": "ent:place:1",
            "world_id": "world:cinder",
            "world_revision": 1,
        },
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
            "regions",
            [{"id": "ent:region:1", "name": "Cinder March"}],
        ),
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
        _topic(
            "equipment_vehicles",
            [
                {"id": "ent:item:1", "name": "Field Ration"},
                {"id": "ent:item:2", "name": "Lamp Cell"},
            ],
        ),
        _topic(
            "actors",
            [
                {
                    "id": "ent:actor:1",
                    "name": "Mara Venn",
                    "location_id": "ent:place:1",
                    "vendor_inventory_item_ids": ["ent:item:1", "ent:item:2"],
                }
            ],
        ),
    ]


def test_integrated_starter_bubble_release_is_certified_and_hashed() -> None:
    report = starter_bubble_release_report(_rows(), _graph())

    assert report["passed"] is True
    certificate = report["materialization"]
    assert certificate["simulation_certified"] is True
    assert certificate["native_certification"]["simulation_certified"] is True
    assert certificate["optional_art_blocks_gameplay"] is False
    assert certificate["content_hash"].startswith("sha256:")
    unhashed = {**certificate, "content_hash": ""}
    assert certificate["content_hash"] == canonical_content_hash(unhashed)
    assert all(certificate["component_statuses"].values())
    assert certificate["starting_market"]["vendor_count"] >= 1
    required = set(certificate["native_certification"]["required_location_ids"])
    materialized = set(certificate["native_certification"]["materialized_location_ids"])
    assert required.issubset(materialized)
    assert certificate["native_certification"]["deferred_location_ids"]


def test_integrated_certificate_is_deterministic() -> None:
    first = starter_bubble_release_report(_rows(), _graph())
    second = starter_bubble_release_report(_rows(), _graph())

    assert first == second
    assert first["materialization"]["content_hash"] == second["materialization"]["content_hash"]


def test_component_failure_propagates_to_integrated_certificate() -> None:
    rows = _rows()
    rows[-1]["candidate"]["entities"][0]["vendor_inventory_item_ids"] = []

    report = starter_bubble_release_report(rows, _graph())

    assert report["passed"] is False
    certificate = report["materialization"]
    assert certificate["component_statuses"]["starting_market"] is False
    issue = next(
        row
        for row in report["issues"]
        if row["code"] == "starter_bubble_release_component_failed"
    )
    assert "starting_market" in issue["evidence"]["failed_component_ids"]


def test_native_simulation_failure_is_blocking(monkeypatch: pytest.MonkeyPatch) -> None:
    original = generation_starter_bubble_release.starter_bubble_certification

    def failed(*args: object, **kwargs: object) -> dict:
        report = dict(original(*args, **kwargs))
        report["simulation_certified"] = False
        report["failed_location_ids"] = ["ent:place:1"]
        return report

    monkeypatch.setattr(
        generation_starter_bubble_release,
        "starter_bubble_certification",
        failed,
    )
    report = starter_bubble_release_report(_rows(), _graph())

    assert report["passed"] is False
    assert any(
        row["code"] == "starter_bubble_native_certification_failed"
        for row in report["issues"]
    )


def test_incomplete_presentation_does_not_block_gameplay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = generation_starter_bubble_release.starter_bubble_certification

    def assets_pending(*args: object, **kwargs: object) -> dict:
        report = dict(original(*args, **kwargs))
        report["presentation_complete"] = False
        report["optional_art_blocks_gameplay"] = False
        return report

    monkeypatch.setattr(
        generation_starter_bubble_release,
        "starter_bubble_certification",
        assets_pending,
    )
    report = starter_bubble_release_report(_rows(), _graph())

    assert report["passed"] is True
    assert report["materialization"]["presentation_complete"] is False
    assert report["checks"]["optional_art_non_blocking"] is True


def test_legacy_graph_without_release6_contract_is_skipped() -> None:
    graph = {
        "metadata": {},
        "nodes": [
            {"topic_id": "places", "metadata": {"field_definitions": []}}
        ],
    }

    report = starter_bubble_release_report([], graph)
    require_valid_starter_bubble_release([], graph)

    assert report["passed"] is True
    certificate = report["materialization"]
    assert certificate["contract_enabled"] is False
    assert certificate["skipped"] is True
    assert certificate["content_hash"].startswith("sha256:")


def test_certified_compilation_fails_before_legacy_compiler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _rows()
    rows[-1]["candidate"]["entities"][0]["vendor_inventory_item_ids"] = []
    called = False

    def legacy(**_kwargs: object) -> object:
        nonlocal called
        called = True
        raise AssertionError("legacy compiler should not run")

    monkeypatch.setattr(
        generation_compilation,
        "compile_world_generation_publication",
        legacy,
    )
    monkeypatch.setattr(
        generation_compilation,
        "_reports",
        lambda values, graph: {
            "starter_bubble_release": starter_bubble_release_report(values, graph)
        },
    )
    monkeypatch.setattr(
        generation_compilation,
        "_graph_audits",
        lambda: ((
            "starter_bubble_release",
            starter_bubble_release_report,
            require_valid_starter_bubble_release,
        ),),
    )
    monkeypatch.setattr(
        generation_compilation,
        "require_unique_canon_identifiers",
        lambda _rows: None,
    )
    monkeypatch.setattr(
        generation_compilation,
        "require_resolved_objective_named_claims",
        lambda _rows: None,
    )

    with pytest.raises(StarterBubbleReleaseCompilationError):
        generation_compilation.compile_world_generation_artifact(
            mode="certified_release",
            run={"graph": _graph()},
            world={},
            topic_rows=rows,
            revision=1,
        )
    assert called is False


def test_transaction_discovers_failed_integrated_release_report() -> None:
    report = publication_transaction_report(
        {
            "run_id": "run:1",
            "world_id": "world:1",
            "status": "review",
            "progress": {},
        },
        {
            "launch_ready": False,
            "missing_requirements": ["starter_bubble_release"],
            "starter_bubble_release": {"passed": False, "issues": []},
        },
    )

    assert report["publishable"] is False
    assert "starter_bubble_release" in report["failed_reports"]
