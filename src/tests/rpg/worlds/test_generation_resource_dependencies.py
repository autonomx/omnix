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
from app.rpg.session.genesis.world_forge_resource_dependencies import (
    deterministic_resource_dependency_signature,
    resource_dependency_components,
)
from app.rpg.worlds import generation_compilation
from app.rpg.worlds.generation_publication import WorldGenerationPublication
from app.rpg.worlds.generation_publication_transaction import (
    publication_transaction_report,
)
from app.rpg.worlds.generation_resource_dependencies import (
    ResourceDependencyCompilationError,
    resource_dependency_issues,
    resource_dependency_report,
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


def _resource_fields(provider_targets: list[str], consumer_targets: list[str]) -> list[dict]:
    return [
        {
            "field_id": "resource_provider_ids",
            "value_type": "entity_ref_list",
            "required": True,
            "allowed_target_domains": provider_targets,
            "semantic_role": "resource_provider",
        },
        {
            "field_id": "resource_consumer_ids",
            "value_type": "entity_ref_list",
            "required": True,
            "allowed_target_domains": consumer_targets,
            "semantic_role": "resource_consumer",
        },
        {
            "field_id": "resource_dependency_signature",
            "value_type": "structured_object",
            "required": True,
            "semantic_role": "resource_dependency_signature",
        },
    ]


def _graph() -> dict:
    return {
        "metadata": {
            "resource_dependency_contract": {
                "schema_version": "rpg_world_resource_dependency_contract_v1",
                "domain_ids": [
                    "groups",
                    "technology_augmentations",
                    "economy_law",
                ],
                "required_before_launch": True,
                "requires_chokepoint": True,
                "requires_substitute": True,
            }
        },
        "nodes": [
            {"topic_id": "places", "metadata": {"field_definitions": []}},
            {
                "topic_id": "groups",
                "metadata": {
                    "resource_dependency_contract": {"required": True},
                    "field_definitions": _resource_fields(["places"], ["places"]),
                },
            },
            {
                "topic_id": "technology_augmentations",
                "metadata": {
                    "resource_dependency_contract": {"required": True},
                    "field_definitions": _resource_fields(["groups"], ["groups"]),
                },
            },
            {
                "topic_id": "economy_law",
                "metadata": {
                    "resource_dependency_contract": {"required": True},
                    "field_definitions": _resource_fields(["groups"], ["places"]),
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
            "provenance": {"generator": "resource_dependency_test"},
        },
    }


def _portfolio_rows(
    *,
    missing_provider: bool = False,
    missing_consumer: bool = False,
    unknown_provider: bool = False,
    identical_sets: bool = False,
    unbounded_supply: bool = False,
    duplicate_signature: bool = False,
    uniform_components: bool = False,
    no_chokepoint: bool = False,
    no_substitute: bool = False,
    narrow_endpoints: bool = False,
) -> list[dict]:
    places = [
        {"id": "ent:place:1", "name": "Red Market"},
        {"id": "ent:place:2", "name": "North Viaduct"},
        {"id": "ent:place:3", "name": "Quiet Ward"},
    ]
    specifications = [
        ("groups", "ent:group:1", "Cedar Compact", ["ent:place:1"], ["ent:place:2"]),
        ("groups", "ent:group:2", "Violet Assembly", ["ent:place:2"], ["ent:place:3"]),
        (
            "technology_augmentations",
            "ent:technology:1",
            "Glass Regulator",
            ["ent:group:1"],
            ["ent:group:2"],
        ),
        (
            "technology_augmentations",
            "ent:technology:2",
            "Harbour Relay",
            ["ent:group:2"],
            ["ent:group:1"],
        ),
        (
            "economy_law",
            "ent:economy:1",
            "Civic Ration Board",
            ["ent:group:1"],
            ["ent:place:3"],
        ),
        (
            "economy_law",
            "ent:economy:2",
            "Transit Credit Office",
            ["ent:group:2"],
            ["ent:place:1"],
        ),
    ]
    by_topic: dict[str, list[dict]] = {
        "groups": [],
        "technology_augmentations": [],
        "economy_law": [],
    }
    for index, (topic_id, entity_id, name, providers, consumers) in enumerate(
        specifications
    ):
        signature = deterministic_resource_dependency_signature(index)
        if duplicate_signature and index == 1:
            signature = deterministic_resource_dependency_signature(0)
        if unbounded_supply and index == 0:
            signature = {**signature, "supply_mode": "self_sufficient"}
        if uniform_components:
            signature = {
                **signature,
                "resource_class": "energy",
                "bottleneck_type": "storage_limit",
                "failure_consequence": "service_shutdown",
            }
        if no_chokepoint:
            signature = {
                **signature,
                "dependency_strength": "supporting",
                "substitute_class": "lower_grade",
                "bottleneck_type": "storage_limit",
            }
        if no_substitute:
            signature = {**signature, "substitute_class": "no_substitute"}
        provider_values = list(providers)
        consumer_values = list(consumers)
        if narrow_endpoints:
            provider_values = ["ent:place:1"] if topic_id == "groups" else ["ent:group:1"]
            consumer_values = ["ent:place:2"] if topic_id != "technology_augmentations" else ["ent:group:2"]
        if missing_provider and index == 0:
            provider_values = []
        if missing_consumer and index == 0:
            consumer_values = []
        if unknown_provider and index == 0:
            provider_values = ["ent:place:unknown"]
        if identical_sets and index == 0:
            consumer_values = list(provider_values)
        by_topic[topic_id].append(
            {
                "id": entity_id,
                "name": name,
                "resource_provider_ids": provider_values,
                "resource_consumer_ids": consumer_values,
                "resource_dependency_signature": signature,
            }
        )
    return [
        _topic("places", places),
        _topic("groups", by_topic["groups"]),
        _topic(
            "technology_augmentations",
            by_topic["technology_augmentations"],
        ),
        _topic("economy_law", by_topic["economy_law"]),
    ]


def test_profile_graph_injects_domain_specific_resource_contracts() -> None:
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    graph = build_profile_topic_graph(profile, campaign_template="classic_fantasy")

    expected_targets = {
        "groups": (["places"], ["places"]),
        "technology_augmentations": (["groups"], ["groups"]),
        "economy_law": (["groups"], ["places"]),
    }
    for domain_id, (provider_targets, consumer_targets) in expected_targets.items():
        node = graph.node_map()[domain_id]
        definitions = {
            str(row.get("field_id")): row
            for row in node.metadata["field_definitions"]
        }
        assert definitions["resource_provider_ids"]["required"] is True
        assert definitions["resource_provider_ids"][
            "allowed_target_domains"
        ] == provider_targets
        assert definitions["resource_consumer_ids"][
            "allowed_target_domains"
        ] == consumer_targets
        assert definitions["resource_dependency_signature"]["required"] is True
        assert node.metadata["resource_dependency_contract"][
            "signature_components"
        ] == list(resource_dependency_components())

    assert graph.metadata["resource_dependency_contract"]["domain_ids"] == [
        "economy_law",
        "groups",
        "technology_augmentations",
    ]


def test_launch_graph_retains_resource_domains_and_dependencies() -> None:
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    graph = build_profile_topic_graph(profile, campaign_template="classic_fantasy")
    launch = build_profile_launch_topic_graph(graph, profile)

    assert {
        "groups",
        "technology_augmentations",
        "economy_law",
    }.issubset(launch.node_map())
    assert set(launch.node_map()["technology_augmentations"].dependencies) >= {
        "groups"
    }
    assert set(launch.node_map()["economy_law"].dependencies) >= {
        "groups",
        "places",
        "technology_augmentations",
    }


def test_deterministic_generation_builds_valid_resource_portfolio() -> None:
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    graph = build_profile_topic_graph(profile, campaign_template="classic_fantasy")
    places = GeneratedTopic(
        topic_id="places",
        entities=tuple({"id": f"ent:place:{index}"} for index in range(1, 7)),
    )
    groups = generate_deterministic_profile_topic(
        graph.node_map()["groups"],
        campaign_context={"world_brief": {"title": "Cinder March"}},
        dependency_topics={
            "setting_rules": GeneratedTopic(topic_id="setting_rules"),
            "places": places,
        },
    )
    technology = generate_deterministic_profile_topic(
        graph.node_map()["technology_augmentations"],
        campaign_context={"world_brief": {"title": "Cinder March"}},
        dependency_topics={
            "setting_rules": GeneratedTopic(topic_id="setting_rules"),
            "groups": groups,
        },
    )
    economy = generate_deterministic_profile_topic(
        graph.node_map()["economy_law"],
        campaign_context={"world_brief": {"title": "Cinder March"}},
        dependency_topics={
            "groups": groups,
            "places": places,
            "technology_augmentations": technology,
        },
    )
    rows = [
        {"topic_id": "places", "candidate": places.as_dict()},
        {"topic_id": "groups", "candidate": groups.as_dict()},
        {
            "topic_id": "technology_augmentations",
            "candidate": technology.as_dict(),
        },
        {"topic_id": "economy_law", "candidate": economy.as_dict()},
    ]

    report = resource_dependency_report(rows, graph.as_dict())

    assert report["passed"] is True
    assert report["checks"]["resource_entity_count"] > 6
    assert report["checks"]["valid_signature_count"] == report["checks"][
        "resource_entity_count"
    ]
    assert report["checks"]["has_chokepoint"] is True
    assert report["checks"]["has_substitute"] is True
    assert all(
        entity["resource_provider_ids"]
        and entity["resource_consumer_ids"]
        and set(entity["resource_provider_ids"])
        != set(entity["resource_consumer_ids"])
        for topic in (groups, technology, economy)
        for entity in topic.entities
    )


def test_diverse_resource_portfolio_passes() -> None:
    report = resource_dependency_report(_portfolio_rows(), _graph())

    assert report["passed"] is True
    assert report["checks"]["resource_entity_count"] == 6
    assert report["checks"]["provider_count"] >= 2
    assert report["checks"]["consumer_count"] >= 2
    assert report["checks"]["has_chokepoint"] is True
    assert report["checks"]["has_substitute"] is True


def test_missing_unknown_and_identical_endpoints_are_blocking() -> None:
    missing = resource_dependency_issues(
        _portfolio_rows(missing_provider=True, missing_consumer=True),
        _graph(),
    )
    unknown = resource_dependency_issues(
        _portfolio_rows(unknown_provider=True),
        _graph(),
    )
    identical = resource_dependency_issues(
        _portfolio_rows(identical_sets=True),
        _graph(),
    )

    assert any(issue.code == "resource_provider_required" for issue in missing)
    assert any(issue.code == "resource_consumer_required" for issue in missing)
    assert any(issue.code == "resource_provider_unknown" for issue in unknown)
    assert any(
        issue.code == "resource_provider_consumer_sets_identical"
        for issue in identical
    )


def test_self_sufficient_supply_claim_is_blocking() -> None:
    issues = resource_dependency_issues(
        _portfolio_rows(unbounded_supply=True),
        _graph(),
    )

    issue = next(
        issue
        for issue in issues
        if issue.code == "unbounded_resource_dependency"
        and issue.resource_entity_id == "ent:group:1"
    )
    assert issue.evidence == {
        "component": "supply_mode",
        "value": "self_sufficient",
    }


def test_duplicate_complete_dependency_signature_is_blocking() -> None:
    issues = resource_dependency_issues(
        _portfolio_rows(duplicate_signature=True),
        _graph(),
    )

    issue = next(
        issue
        for issue in issues
        if issue.code == "duplicate_resource_dependency_signature"
    )
    assert issue.evidence["resource_entity_ids"] == [
        "ent:group:1",
        "ent:group:2",
    ]


def test_resource_portfolio_requires_semantic_diversity() -> None:
    issues = resource_dependency_issues(
        _portfolio_rows(uniform_components=True),
        _graph(),
    )

    components = {
        issue.evidence["component"]
        for issue in issues
        if issue.code == "resource_dependency_portfolio_too_uniform"
    }
    assert components == {
        "resource_class",
        "bottleneck_type",
        "failure_consequence",
    }


def test_resource_portfolio_requires_chokepoints_and_substitutes() -> None:
    no_chokepoint = resource_dependency_issues(
        _portfolio_rows(no_chokepoint=True),
        _graph(),
    )
    no_substitute = resource_dependency_issues(
        _portfolio_rows(no_substitute=True),
        _graph(),
    )

    assert any(
        issue.code == "resource_portfolio_missing_chokepoint"
        for issue in no_chokepoint
    )
    assert any(
        issue.code == "resource_portfolio_missing_substitute"
        for issue in no_substitute
    )


def test_resource_portfolio_requires_multiple_endpoints() -> None:
    issues = resource_dependency_issues(
        _portfolio_rows(narrow_endpoints=True),
        _graph(),
    )

    codes = {issue.code for issue in issues}
    assert "resource_provider_portfolio_too_narrow" in codes
    assert "resource_consumer_portfolio_too_narrow" in codes


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

    with pytest.raises(ResourceDependencyCompilationError):
        generation_compilation.compile_world_generation_certified_artifact(
            run={"run_id": "run:1", "graph": _graph()},
            world={"id": "world:1"},
            topic_rows=_portfolio_rows(unbounded_supply=True),
            revision=1,
        )

    assert called is False


def test_diagnostic_compilation_retains_resource_report(
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
        topic_rows=_portfolio_rows(missing_provider=True),
        revision=1,
    )

    report = artifact.certification["resource_dependencies"]
    assert report["passed"] is False
    assert artifact.certification["launch_ready"] is False
    assert "resource_dependencies" in artifact.certification[
        "missing_requirements"
    ]


def test_publication_transaction_surfaces_resource_failure() -> None:
    report = publication_transaction_report(
        {
            "run_id": "run:1",
            "world_id": "world:1",
            "status": "review",
            "progress": {"publication_blocked": False},
        },
        {
            "launch_ready": False,
            "missing_requirements": ["resource_dependencies"],
            "resource_dependencies": {
                "passed": False,
                "issues": [{"code": "resource_provider_required"}],
            },
        },
    )

    assert report["publishable"] is False
    assert "resource_dependencies" in report["failed_reports"]
