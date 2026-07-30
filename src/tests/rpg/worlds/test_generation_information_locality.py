from __future__ import annotations

import pytest

from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.session.genesis.world_forge_information_locality import (
    deterministic_information_locality_signature,
    information_locality_components,
)
from app.rpg.session.genesis.world_forge_profile_deterministic import (
    generate_deterministic_profile_topic,
)
from app.rpg.session.genesis.world_forge_profile_generation import default_profile_registry
from app.rpg.session.genesis.world_forge_profile_graph import build_profile_topic_graph
from app.rpg.session.genesis.world_forge_route_effects import (
    deterministic_route_effect_signature,
)
from app.rpg.worlds import generation_compilation
from app.rpg.worlds.generation_information_locality import (
    InformationLocalityCompilationError,
    information_locality_issues,
    information_locality_report,
)
from app.rpg.worlds.generation_publication_transaction import (
    publication_transaction_report,
)


def _graph() -> dict:
    return {
        "nodes": [
            {"topic_id": "places", "metadata": {"field_definitions": []}},
            {
                "topic_id": "groups",
                "metadata": {
                    "field_definitions": [
                        {
                            "field_id": "information_anchor_place_id",
                            "value_type": "entity_ref",
                            "required": True,
                            "allowed_target_domains": ["places"],
                        },
                        {
                            "field_id": "information_place_ids",
                            "value_type": "entity_ref_list",
                            "required": True,
                            "allowed_target_domains": ["places"],
                        },
                        {
                            "field_id": "information_locality_signature",
                            "value_type": "structured_object",
                            "required": True,
                        },
                    ]
                },
            },
        ]
    }


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


def _rows(*, duplicate: bool = False) -> list[dict]:
    places = []
    groups = []
    for index in range(4):
        anchor = f"ent:place:{index + 1}"
        endpoint = f"ent:place:{((index + 1) % 4) + 1}"
        places.append(
            {
                "id": anchor,
                "connected_place_ids": [endpoint],
                "route_effects": {
                    endpoint: deterministic_route_effect_signature(index)
                },
            }
        )
        groups.append(
            {
                "id": f"ent:group:{index + 1}",
                "information_anchor_place_id": anchor,
                "information_place_ids": [anchor, endpoint],
                "information_locality_signature": (
                    deterministic_information_locality_signature(0)
                    if duplicate and index == 1
                    else deterministic_information_locality_signature(index)
                ),
            }
        )
    return [_topic("places", places), _topic("groups", groups)]


def test_profile_graph_injects_information_locality_fields() -> None:
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    graph = build_profile_topic_graph(profile, campaign_template="classic_fantasy")
    groups = graph.node_map()["groups"]
    fields = {
        str(row.get("field_id")): row
        for row in groups.metadata["field_definitions"]
    }

    assert fields["information_anchor_place_id"]["required"] is True
    assert fields["information_anchor_place_id"]["allowed_target_domains"] == [
        "places"
    ]
    assert fields["information_place_ids"]["required"] is True
    assert fields["information_locality_signature"]["required"] is True
    assert "places" in groups.dependencies
    assert list(information_locality_components()) == [
        "channel_type",
        "latency_band",
        "verification_method",
        "distortion_risk",
        "interception_risk",
        "blackout_condition",
        "update_cadence",
        "confidence_decay",
    ]


def test_deterministic_groups_build_route_consistent_information_locality() -> None:
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    graph = build_profile_topic_graph(
        profile,
        campaign_template="classic_fantasy",
        depth="epic",
    )
    group_node = graph.node_map()["groups"]
    place_count = max(group_node.target_count + 2, 12)
    places = []
    for index in range(place_count):
        anchor = f"ent:place:{index + 1}"
        endpoint = f"ent:place:{((index + 1) % place_count) + 1}"
        places.append(
            {
                "id": anchor,
                "connected_place_ids": [endpoint],
                "route_effects": {
                    endpoint: deterministic_route_effect_signature(index)
                },
            }
        )
    dependencies = {
        domain_id: GeneratedTopic(
            topic_id=domain_id,
            entities=(
                tuple(places)
                if domain_id == "places"
                else tuple(
                    {"id": f"ent:{domain_id}:{index}"}
                    for index in range(1, 20)
                )
            ),
        )
        for domain_id in group_node.dependencies
    }
    groups = generate_deterministic_profile_topic(
        group_node,
        campaign_context={"world_brief": {"title": "Cinder March"}},
        dependency_topics=dependencies,
    )
    rows = [
        _topic("places", places),
        {"topic_id": "groups", "candidate": groups.as_dict()},
    ]

    report = information_locality_report(rows, graph.as_dict())

    assert report["passed"] is True
    assert report["checks"]["group_count"] == len(groups.entities)
    assert all(
        entity["information_anchor_place_id"]
        in entity["information_place_ids"]
        for entity in groups.entities
    )


def test_missing_unknown_and_universal_information_reach_are_blocking() -> None:
    rows = _rows()
    rows[1]["candidate"]["entities"][0]["information_place_ids"] = []
    missing = information_locality_issues(rows, _graph())
    rows = _rows()
    rows[1]["candidate"]["entities"][0]["information_place_ids"] = [
        "ent:place:missing"
    ]
    unknown = information_locality_issues(rows, _graph())
    rows = _rows()
    rows[1]["candidate"]["entities"][0]["information_place_ids"] = [
        f"ent:place:{index}" for index in range(1, 5)
    ]
    universal = information_locality_issues(rows, _graph())

    assert any(row.code == "information_reach_required" for row in missing)
    assert any(row.code == "information_place_reference_invalid" for row in unknown)
    assert any(row.code == "information_reach_universal" for row in universal)


def test_unbounded_and_route_impossible_latency_are_blocking() -> None:
    rows = _rows()
    rows[1]["candidate"]["entities"][0]["information_locality_signature"][
        "latency_band"
    ] = "instant"
    unbounded = information_locality_issues(rows, _graph())
    rows = _rows()
    group = rows[1]["candidate"]["entities"][1]
    group["information_locality_signature"]["latency_band"] = "same_day"
    impossible = information_locality_issues(rows, _graph())

    assert any(
        row.code == "information_locality_component_unbounded:latency_band"
        for row in unbounded
    )
    assert any(row.code == "information_latency_faster_than_route" for row in impossible)


def test_duplicate_and_uniform_information_networks_are_blocking() -> None:
    duplicate = information_locality_issues(_rows(duplicate=True), _graph())
    rows = _rows()
    for group in rows[1]["candidate"]["entities"]:
        group["information_locality_signature"] = {
            **group["information_locality_signature"],
            "channel_type": "courier_chain",
            "latency_band": "one_week",
            "distortion_risk": "politically_filtered",
        }
    uniform = information_locality_issues(rows, _graph())

    assert any(
        row.code == "duplicate_information_locality_signature"
        for row in duplicate
    )
    assert {
        row.evidence["component"]
        for row in uniform
        if row.code == "information_locality_component_uniform"
    } == {"channel_type", "latency_band", "distortion_risk"}


def test_certified_compilation_fails_before_legacy_compiler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _rows()
    rows[1]["candidate"]["entities"][0].pop(
        "information_locality_signature"
    )
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
            "information_locality": information_locality_report(values, graph)
        },
    )
    monkeypatch.setattr(
        generation_compilation,
        "_graph_audits",
        lambda: ((
            "information_locality",
            information_locality_report,
            generation_compilation.extension_audits()[1][2],
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

    with pytest.raises(InformationLocalityCompilationError):
        generation_compilation.compile_world_generation_artifact(
            mode="certified_release",
            run={"graph": _graph()},
            world={},
            topic_rows=rows,
            revision=1,
        )
    assert called is False


def test_transaction_discovers_failed_information_locality_report() -> None:
    report = publication_transaction_report(
        {
            "run_id": "run:1",
            "world_id": "world:1",
            "status": "review",
            "progress": {},
        },
        {
            "launch_ready": False,
            "missing_requirements": ["information_locality"],
            "information_locality": {"passed": False, "issues": []},
        },
    )

    assert report["publishable"] is False
    assert "information_locality" in report["failed_reports"]
