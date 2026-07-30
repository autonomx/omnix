from __future__ import annotations

import pytest

from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.session.genesis.world_forge_profile_deterministic import (
    generate_deterministic_profile_topic,
)
from app.rpg.session.genesis.world_forge_profile_generation import (
    default_profile_registry,
)
from app.rpg.session.genesis.world_forge_profile_graph import (
    build_profile_launch_topic_graph,
    build_profile_topic_graph,
)
from app.rpg.session.genesis.world_forge_spatial_routes import (
    deterministic_spatial_route_signature,
    minimum_route_count,
    spatial_route_components,
)
from app.rpg.worlds import generation_compilation
from app.rpg.worlds.generation_publication import WorldGenerationPublication
from app.rpg.worlds.generation_publication_transaction import (
    publication_transaction_report,
)
from app.rpg.worlds.generation_spatial_reachability import (
    SpatialReachabilityCompilationError,
    spatial_reachability_issues,
    spatial_reachability_report,
)


class _Document:
    def model_dump(self, *, mode: str) -> dict:
        assert mode == "json"
        return {"kind": "revision"}


class _Release:
    artifact_stage = "playtested"
    runtime_seed = {"content_hash": "sha256:runtime"}
    materialization = {"content_hash": "sha256:materialization"}
    playtest_report = {"content_hash": "sha256:playtest"}

    def model_dump(self, *, mode: str) -> dict:
        assert mode == "json"
        return {"kind": "release"}


def _publication() -> WorldGenerationPublication:
    return WorldGenerationPublication(
        world_revision=_Document(),  # type: ignore[arg-type]
        world_release=_Release(),  # type: ignore[arg-type]
        certification={
            "launch_ready": True,
            "missing_requirements": [],
            "consistency_report": {
                "passed": True,
                "issues": [],
                "patches": [],
                "checks": {},
            },
        },
    )


def _graph(*, depth: str = "standard", minimum_routes: int = 5) -> dict:
    return {
        "depth": depth,
        "metadata": {
            "spatial_route_contract": {
                "schema_version": "rpg_world_spatial_route_contract_v1",
                "domain_ids": ["places"],
                "required_before_launch": True,
                "depth": depth,
                "place_count": 6,
                "minimum_route_count": minimum_routes,
            }
        },
        "nodes": [
            {
                "topic_id": "places",
                "metadata": {
                    "spatial_route_contract": {
                        "required": True,
                        "connection_field": "connected_place_ids",
                        "signature_field": "travel_route_signature",
                    },
                    "field_definitions": [
                        {
                            "field_id": "connected_place_ids",
                            "value_type": "entity_ref_list",
                            "required": True,
                            "allowed_target_domains": ["places"],
                            "semantic_role": "travel_route",
                        },
                        {
                            "field_id": "travel_route_signature",
                            "value_type": "structured_object",
                            "required": True,
                            "semantic_role": "travel_route_signature",
                        },
                    ],
                },
            }
        ],
    }


def _topic(entities: list[dict]) -> dict:
    return {
        "topic_id": "places",
        "candidate": {
            "topic_id": "places",
            "documents": [],
            "entities": entities,
            "facts": [],
            "relationships": [],
            "knowledge_rules": [],
            "story_threads": [],
            "provenance": {"generator": "spatial_reachability_test"},
        },
    }


def _portfolio_rows(
    *,
    disconnected: bool = False,
    sparse_chain: bool = False,
    missing_connection: bool = False,
    unknown_target: bool = False,
    self_target: bool = False,
    unbounded_time: bool = False,
    uniform_routes: bool = False,
    bounded_portal: bool = False,
) -> list[dict]:
    names = (
        "Red Market",
        "North Viaduct",
        "Quiet Ward",
        "Copper Terminal",
        "Violet Quay",
        "Glass Orchard",
    )
    if disconnected:
        connections = (
            (2, 3),
            (1, 3),
            (1, 2),
            (5, 6),
            (4, 6),
            (4, 5),
        )
    elif sparse_chain:
        connections = (
            (2,),
            (1, 3),
            (2, 4),
            (3, 5),
            (4, 6),
            (5,),
        )
    else:
        connections = (
            (2, 3),
            (3, 4),
            (4, 5),
            (5, 6),
            (6, 1),
            (1, 2),
        )
    places = []
    for index, name in enumerate(names):
        signature = deterministic_spatial_route_signature(index)
        if unbounded_time and index == 0:
            signature = {**signature, "travel_time_band": "instant"}
        if uniform_routes:
            signature = {
                **signature,
                "travel_time_band": "district_hour",
                "access_mode": "foot_route",
                "route_blocker": "checkpoint",
                "failure_condition": "closure",
            }
        if bounded_portal and index == 0:
            signature = {
                **signature,
                "travel_time_band": "ritual_minutes",
                "access_mode": "portal_gate",
                "route_blocker": "keyed_threshold",
                "failure_condition": "misroute",
            }
        target_ids = [f"ent:place:{value}" for value in connections[index]]
        if missing_connection and index == 0:
            target_ids = []
        if unknown_target and index == 0:
            target_ids = ["ent:place:unknown"]
        if self_target and index == 0:
            target_ids = ["ent:place:1"]
        places.append(
            {
                "id": f"ent:place:{index + 1}",
                "name": name,
                "connected_place_ids": target_ids,
                "travel_route_signature": signature,
            }
        )
    return [_topic(places)]


def test_profile_graph_injects_depth_scaled_spatial_contract() -> None:
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    graph = build_profile_topic_graph(
        profile,
        campaign_template="classic_fantasy",
        depth="standard",
    )
    place_node = graph.node_map()["places"]
    definitions = {
        str(row.get("field_id")): row
        for row in place_node.metadata["field_definitions"]
    }

    assert definitions["connected_place_ids"]["required"] is True
    assert definitions["connected_place_ids"]["allowed_target_domains"] == [
        "places"
    ]
    assert definitions["travel_route_signature"]["required"] is True
    assert place_node.metadata["spatial_route_contract"][
        "signature_components"
    ] == list(spatial_route_components())
    assert graph.metadata["spatial_route_contract"]["minimum_route_count"] == (
        minimum_route_count(place_node.target_count, "standard")
    )


def test_spatial_route_floor_scales_with_depth() -> None:
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    floors = []
    for depth in ("quick", "standard", "epic"):
        graph = build_profile_topic_graph(
            profile,
            campaign_template="classic_fantasy",
            depth=depth,
        )
        floors.append(graph.metadata["spatial_route_contract"]["minimum_route_count"])

    assert floors[0] < floors[1] < floors[2]


def test_launch_graph_retains_spatial_domain() -> None:
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    graph = build_profile_topic_graph(profile, campaign_template="classic_fantasy")
    launch = build_profile_launch_topic_graph(graph, profile)

    assert "places" in launch.node_map()
    assert launch.node_map()["places"].required_before_launch is True


def test_deterministic_place_generation_emits_connected_bounded_routes() -> None:
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    graph = build_profile_topic_graph(profile, campaign_template="classic_fantasy")
    place_node = graph.node_map()["places"]
    dependencies = {
        "regions": GeneratedTopic(
            topic_id="regions",
            entities=tuple({"id": f"ent:region:{index}"} for index in range(1, 5)),
        )
    }

    topic = generate_deterministic_profile_topic(
        place_node,
        campaign_context={
            "world_brief": {"title": "Cinder March", "genre": "fantasy"}
        },
        dependency_topics=dependencies,
    )
    place_ids = {str(entity["id"]) for entity in topic.entities}
    rows = [
        {
            "topic_id": "places",
            "candidate": topic.as_dict(),
        }
    ]
    report = spatial_reachability_report(rows, graph.as_dict())

    assert report["passed"] is True
    assert report["checks"]["place_count"] == place_node.target_count
    assert report["checks"]["route_count"] >= report["checks"][
        "minimum_route_count"
    ]
    assert all(
        entity["connected_place_ids"]
        and str(entity["id"]) not in entity["connected_place_ids"]
        and set(entity["connected_place_ids"]).issubset(place_ids)
        for entity in topic.entities
    )
    assert all(
        set(entity["travel_route_signature"]) == set(spatial_route_components())
        for entity in topic.entities
    )


def test_connected_route_portfolio_passes() -> None:
    report = spatial_reachability_report(_portfolio_rows(), _graph())

    assert report["passed"] is True
    assert report["checks"]["place_count"] == 6
    assert report["checks"]["route_count"] >= 5
    assert report["checks"]["connected_component_count"] == 1


def test_disconnected_graph_is_blocking_even_with_enough_routes() -> None:
    issues = spatial_reachability_issues(
        _portfolio_rows(disconnected=True),
        _graph(),
    )

    issue = next(
        issue for issue in issues if issue.code == "spatial_graph_disconnected"
    )
    assert len(issue.evidence["components"]) == 2


def test_connected_but_sparse_graph_fails_epic_route_floor() -> None:
    issues = spatial_reachability_issues(
        _portfolio_rows(sparse_chain=True),
        _graph(depth="epic", minimum_routes=8),
    )

    issue = next(
        issue
        for issue in issues
        if issue.code == "spatial_route_count_below_depth_floor"
    )
    assert issue.evidence["route_count"] == 5
    assert issue.evidence["minimum_route_count"] == 8


def test_missing_unknown_and_self_endpoints_are_blocking() -> None:
    missing = spatial_reachability_issues(
        _portfolio_rows(missing_connection=True),
        _graph(),
    )
    unknown = spatial_reachability_issues(
        _portfolio_rows(unknown_target=True),
        _graph(),
    )
    self_reference = spatial_reachability_issues(
        _portfolio_rows(self_target=True),
        _graph(),
    )

    assert any(issue.code == "place_connection_required" for issue in missing)
    assert any(issue.code == "spatial_route_target_unknown" for issue in unknown)
    assert any(issue.code == "spatial_route_self_reference" for issue in self_reference)


def test_instant_travel_claim_is_blocking() -> None:
    issues = spatial_reachability_issues(
        _portfolio_rows(unbounded_time=True),
        _graph(),
    )

    issue = next(
        issue
        for issue in issues
        if issue.code == "unbounded_spatial_route"
        and issue.place_id == "ent:place:1"
    )
    assert issue.evidence == {
        "component": "travel_time_band",
        "value": "instant",
    }


def test_bounded_portal_route_is_valid() -> None:
    report = spatial_reachability_report(
        _portfolio_rows(bounded_portal=True),
        _graph(),
    )

    assert report["passed"] is True


def test_large_route_portfolio_requires_constraint_diversity() -> None:
    issues = spatial_reachability_issues(
        _portfolio_rows(uniform_routes=True),
        _graph(),
    )

    components = {
        issue.evidence["component"]
        for issue in issues
        if issue.code == "spatial_route_portfolio_too_uniform"
    }
    assert components == {
        "travel_time_band",
        "access_mode",
        "route_blocker",
        "failure_condition",
    }


def test_certified_compilation_fails_before_legacy_compiler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def _compile(**_kwargs: object) -> WorldGenerationPublication:
        nonlocal called
        called = True
        return _publication()

    monkeypatch.setattr(
        generation_compilation,
        "compile_world_generation_publication",
        _compile,
    )

    with pytest.raises(SpatialReachabilityCompilationError):
        generation_compilation.compile_world_generation_certified_artifact(
            run={"run_id": "run:1", "graph": _graph()},
            world={"id": "world:1"},
            topic_rows=_portfolio_rows(disconnected=True),
            revision=1,
        )

    assert called is False


def test_diagnostic_compilation_retains_spatial_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        generation_compilation,
        "compile_world_generation_publication",
        lambda **_kwargs: _publication(),
    )

    artifact = generation_compilation.compile_world_generation_diagnostic_draft(
        run={"run_id": "run:1", "graph": _graph()},
        world={"id": "world:1"},
        topic_rows=_portfolio_rows(missing_connection=True),
        revision=1,
    )

    report = artifact.certification["spatial_reachability"]
    assert report["passed"] is False
    assert artifact.certification["launch_ready"] is False
    assert "spatial_reachability" in artifact.certification[
        "missing_requirements"
    ]


def test_publication_transaction_surfaces_spatial_failure() -> None:
    report = publication_transaction_report(
        {
            "run_id": "run:1",
            "world_id": "world:1",
            "status": "review",
            "progress": {"publication_blocked": False},
        },
        {
            "launch_ready": False,
            "missing_requirements": ["spatial_reachability"],
            "spatial_reachability": {
                "passed": False,
                "issues": [{"code": "spatial_graph_disconnected"}],
            },
        },
    )

    assert report["publishable"] is False
    assert "spatial_reachability" in report["failed_reports"]
