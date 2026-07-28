from __future__ import annotations

import pytest

from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.session.genesis.world_forge_network_constraints import (
    deterministic_network_constraint_signature,
    network_constraint_components,
)
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
from app.rpg.worlds import generation_compilation
from app.rpg.worlds.generation_network_constraints import (
    NetworkConstraintCompilationError,
    network_constraint_issues,
    network_constraint_report,
)
from app.rpg.worlds.generation_publication import WorldGenerationPublication
from app.rpg.worlds.generation_publication_transaction import (
    publication_transaction_report,
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


def _graph() -> dict:
    return {
        "metadata": {
            "runtime_capabilities": {"digital_spaces": True},
            "network_constraint_contract": {
                "schema_version": "rpg_world_network_constraint_contract_v1",
                "capability": "digital_spaces",
                "domain_ids": ["networks"],
                "required_before_launch": True,
            },
        },
        "nodes": [
            {
                "topic_id": "groups",
                "metadata": {"field_definitions": []},
            },
            {
                "topic_id": "places",
                "metadata": {"field_definitions": []},
            },
            {
                "topic_id": "networks",
                "metadata": {
                    "network_constraint_contract": {
                        "required": True,
                        "capability": "digital_spaces",
                        "controller_field": "controller_group_ids",
                        "coverage_field": "covered_place_ids",
                        "signature_field": "network_constraint_signature",
                    },
                    "field_definitions": [
                        {
                            "field_id": "controller_group_ids",
                            "value_type": "entity_ref_list",
                            "required": True,
                            "allowed_target_domains": ["groups"],
                            "semantic_role": "network_controller",
                        },
                        {
                            "field_id": "covered_place_ids",
                            "value_type": "entity_ref_list",
                            "required": True,
                            "allowed_target_domains": ["places"],
                            "semantic_role": "network_coverage",
                        },
                        {
                            "field_id": "network_constraint_signature",
                            "value_type": "structured_object",
                            "required": True,
                            "semantic_role": "network_constraint_signature",
                        },
                    ],
                },
            },
        ],
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
            "provenance": {"generator": "network_constraint_test"},
        },
    }


def _portfolio_rows(
    *,
    duplicate_signature: bool = False,
    unbounded_blind_spot: bool = False,
    uniform_limits: bool = False,
    missing_controller: bool = False,
    missing_coverage: bool = False,
    malformed_signature: bool = False,
) -> list[dict]:
    group_names = (
        "Cedar Authority",
        "Violet Directorate",
        "Harbour Cooperative",
        "Glass Tribunal",
    )
    place_names = (
        "Red Market",
        "North Viaduct",
        "Quiet Ward",
        "Copper Terminal",
    )
    network_names = (
        "Aegis Relay",
        "Lattice Exchange",
        "Quiet Channel",
        "Harbour Mesh",
    )
    groups = [
        {"id": f"ent:group:{index}", "name": name}
        for index, name in enumerate(group_names, start=1)
    ]
    places = [
        {"id": f"ent:place:{index}", "name": name}
        for index, name in enumerate(place_names, start=1)
    ]
    networks = []
    for index, name in enumerate(network_names):
        signature = deterministic_network_constraint_signature(index)
        if duplicate_signature and index == 1:
            signature = deterministic_network_constraint_signature(0)
        if unbounded_blind_spot and index == 0:
            signature = {**signature, "blind_spot": "none"}
        if uniform_limits:
            signature = {
                **signature,
                "blind_spot": "maintenance_tunnels",
                "failure_mode": "partition",
            }
        if malformed_signature and index == 0:
            signature = {"coverage_scope": "district_mesh"}
        networks.append(
            {
                "id": f"ent:network:{index + 1}",
                "name": name,
                "controller_group_ids": (
                    []
                    if missing_controller and index == 0
                    else [f"ent:group:{index + 1}"]
                ),
                "covered_place_ids": (
                    []
                    if missing_coverage and index == 0
                    else [f"ent:place:{index + 1}"]
                ),
                "network_constraint_signature": signature,
            }
        )
    return [
        _topic("groups", groups),
        _topic("places", places),
        _topic("networks", networks),
    ]


def test_cyberpunk_graph_enables_required_network_contract() -> None:
    profile = default_profile_registry().resolve("cyberpunk")
    assert profile is not None
    graph = build_profile_topic_graph(profile, campaign_template="cyberpunk")
    network_node = graph.node_map()["networks"]
    definitions = {
        str(row.get("field_id")): row
        for row in network_node.metadata["field_definitions"]
    }

    assert graph.metadata["network_constraint_contract"]["domain_ids"] == [
        "networks"
    ]
    assert definitions["controller_group_ids"]["required"] is True
    assert definitions["covered_place_ids"]["required"] is True
    assert definitions["network_constraint_signature"]["required"] is True
    assert network_node.metadata["network_constraint_contract"][
        "signature_components"
    ] == list(network_constraint_components())


def test_fantasy_graph_does_not_enable_network_contract() -> None:
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    graph = build_profile_topic_graph(profile, campaign_template="classic_fantasy")
    network_node = graph.node_map()["networks"]
    definitions = {
        str(row.get("field_id")): row
        for row in network_node.metadata["field_definitions"]
    }

    assert "network_constraint_contract" not in graph.metadata
    assert "network_constraint_contract" not in network_node.metadata
    assert "covered_place_ids" not in definitions
    assert "network_constraint_signature" not in definitions
    assert definitions["controller_group_ids"]["required"] is False


def test_cyberpunk_launch_graph_includes_network_domain_and_dependencies() -> None:
    profile = default_profile_registry().resolve("cyberpunk")
    assert profile is not None
    graph = build_profile_topic_graph(profile, campaign_template="cyberpunk")
    launch = build_profile_launch_topic_graph(graph, profile)

    assert "networks" in launch.node_map()
    assert set(launch.node_map()["networks"].dependencies) >= {
        "groups",
        "places",
        "technology_augmentations",
    }


def test_deterministic_network_generation_emits_bounded_varied_signatures() -> None:
    profile = default_profile_registry().resolve("cyberpunk")
    assert profile is not None
    graph = build_profile_topic_graph(profile, campaign_template="cyberpunk")
    network_node = graph.node_map()["networks"]
    dependencies = {
        "groups": GeneratedTopic(
            topic_id="groups",
            entities=tuple({"id": f"ent:group:{index}"} for index in range(1, 5)),
        ),
        "places": GeneratedTopic(
            topic_id="places",
            entities=tuple({"id": f"ent:place:{index}"} for index in range(1, 5)),
        ),
        "technology_augmentations": GeneratedTopic(
            topic_id="technology_augmentations",
            entities=tuple(
                {"id": f"ent:technology:{index}"} for index in range(1, 5)
            ),
        ),
    }

    topic = generate_deterministic_profile_topic(
        network_node,
        campaign_context={
            "world_brief": {"title": "Neon Meridian", "genre": "cyberpunk"}
        },
        dependency_topics=dependencies,
    )

    signatures = [
        dict(entity["network_constraint_signature"]) for entity in topic.entities
    ]
    assert all(
        set(signature) == set(network_constraint_components())
        for signature in signatures
    )
    assert len(
        {tuple(sorted(signature.items())) for signature in signatures}
    ) == len(signatures)
    assert all(entity["controller_group_ids"] for entity in topic.entities)
    assert all(entity["covered_place_ids"] for entity in topic.entities)
    assert all(signature["blind_spot"] != "none" for signature in signatures)
    assert all(signature["failure_mode"] != "none" for signature in signatures)


def test_diverse_bounded_network_portfolio_passes() -> None:
    report = network_constraint_report(_portfolio_rows(), _graph())

    assert report["passed"] is True
    assert report["checks"]["network_count"] == 4
    assert report["checks"]["valid_signature_count"] == 4
    assert report["checks"]["controller_count"] == 4
    assert report["checks"]["covered_place_count"] == 4


def test_missing_controller_and_coverage_are_blocking() -> None:
    issues = network_constraint_issues(
        _portfolio_rows(missing_controller=True, missing_coverage=True),
        _graph(),
    )

    codes = {
        issue.code
        for issue in issues
        if issue.network_id == "ent:network:1"
    }
    assert "network_controller_required" in codes
    assert "network_coverage_required" in codes


def test_malformed_signature_reports_missing_components() -> None:
    issues = network_constraint_issues(
        _portfolio_rows(malformed_signature=True),
        _graph(),
    )

    assert any(
        issue.code == "network_constraint_component_required:blind_spot"
        and issue.network_id == "ent:network:1"
        for issue in issues
    )


def test_unbounded_surveillance_claim_is_blocking() -> None:
    issues = network_constraint_issues(
        _portfolio_rows(unbounded_blind_spot=True),
        _graph(),
    )

    issue = next(
        issue
        for issue in issues
        if issue.code == "unbounded_network_constraint"
        and issue.network_id == "ent:network:1"
    )
    assert issue.evidence == {"component": "blind_spot", "value": "none"}


def test_duplicate_complete_network_signature_is_blocking() -> None:
    issues = network_constraint_issues(
        _portfolio_rows(duplicate_signature=True),
        _graph(),
    )

    issue = next(
        issue
        for issue in issues
        if issue.code == "duplicate_network_constraint_signature"
    )
    assert issue.evidence["network_ids"] == [
        "ent:network:1",
        "ent:network:2",
    ]


def test_network_portfolio_requires_distinct_blind_spots_and_failures() -> None:
    issues = network_constraint_issues(
        _portfolio_rows(uniform_limits=True),
        _graph(),
    )

    components = {
        issue.evidence["component"]
        for issue in issues
        if issue.code == "network_constraint_portfolio_too_uniform"
    }
    assert components == {"blind_spot", "failure_mode"}


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

    with pytest.raises(NetworkConstraintCompilationError):
        generation_compilation.compile_world_generation_certified_artifact(
            run={"run_id": "run:1", "graph": _graph()},
            world={"id": "world:1"},
            topic_rows=_portfolio_rows(unbounded_blind_spot=True),
            revision=1,
        )

    assert called is False


def test_diagnostic_compilation_retains_network_report(
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
        topic_rows=_portfolio_rows(missing_coverage=True),
        revision=1,
    )

    report = artifact.certification["network_constraints"]
    assert report["passed"] is False
    assert artifact.certification["launch_ready"] is False
    assert "network_constraints" in artifact.certification["missing_requirements"]


def test_publication_transaction_surfaces_network_failure() -> None:
    report = publication_transaction_report(
        {
            "run_id": "run:1",
            "world_id": "world:1",
            "status": "review",
            "progress": {"publication_blocked": False},
        },
        {
            "launch_ready": False,
            "missing_requirements": ["network_constraints"],
            "network_constraints": {
                "passed": False,
                "issues": [{"code": "network_coverage_required"}],
            },
        },
    )

    assert report["publishable"] is False
    assert "network_constraints" in report["failed_reports"]
