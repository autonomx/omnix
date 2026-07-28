from __future__ import annotations

import pytest

from app.rpg.session.genesis.world_forge_economic_scale import (
    deterministic_economic_scale_signature,
    economic_scale_components,
)
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
from app.rpg.worlds import generation_compilation
from app.rpg.worlds.generation_economic_scale import (
    EconomicScaleCompilationError,
    economic_scale_issues,
    economic_scale_report,
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
            "economic_scale_contract": {
                "schema_version": "rpg_world_economic_scale_contract_v1",
                "domain_ids": ["places", "economy_law"],
                "required_before_launch": True,
            }
        },
        "nodes": [
            {
                "topic_id": "places",
                "metadata": {
                    "economic_scale_contract": {
                        "required": True,
                        "signature_field": "economic_scale_signature",
                        "coverage_field": "",
                        "expected_scope": "place_population",
                    },
                    "field_definitions": [
                        {
                            "field_id": "economic_scale_signature",
                            "value_type": "structured_object",
                            "required": True,
                        }
                    ],
                },
            },
            {
                "topic_id": "economy_law",
                "metadata": {
                    "economic_scale_contract": {
                        "required": True,
                        "signature_field": "economic_scale_signature",
                        "coverage_field": "affected_place_ids",
                        "expected_scope": "service_system",
                    },
                    "field_definitions": [
                        {
                            "field_id": "affected_place_ids",
                            "value_type": "entity_ref_list",
                            "required": True,
                            "allowed_target_domains": ["places"],
                        },
                        {
                            "field_id": "economic_scale_signature",
                            "value_type": "structured_object",
                            "required": True,
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
            "provenance": {"generator": "economic_scale_test"},
        },
    }


def _portfolio_rows(
    *,
    missing_signature: bool = False,
    scope_mismatch: bool = False,
    unknown_band: bool = False,
    workforce_exceeds_population: bool = False,
    reach_exceeds_population: bool = False,
    throughput_exceeds_workforce: bool = False,
    scarcity_reserve_mismatch: bool = False,
    missing_coverage: bool = False,
    narrow_coverage: bool = False,
    duplicate_signature: bool = False,
    uniform_components: bool = False,
    unbounded_throughput: bool = False,
) -> list[dict]:
    place_names = (
        "Red Market",
        "North Viaduct",
        "Quiet Ward",
        "Copper Terminal",
    )
    system_names = (
        "Civic Ration Board",
        "Transit Credit Office",
        "Harbour Tariff House",
    )
    places = []
    for index, name in enumerate(place_names):
        signature = deterministic_economic_scale_signature(
            index,
            scope="place",
        )
        places.append(
            {
                "id": f"ent:place:{index + 1}",
                "name": name,
                "economic_scale_signature": signature,
            }
        )
    systems = []
    for index, name in enumerate(system_names):
        signature = deterministic_economic_scale_signature(
            index + 11,
            scope="world_system",
        )
        if duplicate_signature and index == 1:
            signature = deterministic_economic_scale_signature(
                11,
                scope="world_system",
            )
        if scope_mismatch and index == 0:
            signature = {**signature, "scale_scope": "place_population"}
        if unknown_band and index == 0:
            signature = {**signature, "price_basis": "market_magic"}
        if workforce_exceeds_population and index == 0:
            signature = {
                **signature,
                "served_population_band": "dozens",
                "workforce_band": "thousands",
            }
        if reach_exceeds_population and index == 0:
            signature = {
                **signature,
                "served_population_band": "dozens",
                "service_reach_band": "regional",
            }
        if throughput_exceeds_workforce and index == 0:
            signature = {
                **signature,
                "workforce_band": "individual",
                "throughput_band": "continuous_bulk",
            }
        if scarcity_reserve_mismatch and index == 0:
            signature = {
                **signature,
                "scarcity_level": "critical",
                "reserve_horizon": "months",
            }
        if unbounded_throughput and index == 0:
            signature = {**signature, "throughput_band": "unlimited"}
        if uniform_components:
            signature = {
                **signature,
                "served_population_band": "thousands",
                "throughput_band": "hundreds_per_day",
                "price_basis": "regulated_tariff",
                "scarcity_level": "constrained",
                "reserve_horizon": "weeks",
            }
        affected = [
            f"ent:place:{index + 1}",
            f"ent:place:{index + 2}",
        ]
        if missing_coverage and index == 0:
            affected = []
        if narrow_coverage and index == 0:
            affected = ["ent:place:1"]
            signature = {
                **signature,
                "served_population_band": "hundreds_of_thousands",
                "service_reach_band": "regional",
            }
        systems.append(
            {
                "id": f"ent:economy:{index + 1}",
                "name": name,
                "affected_place_ids": affected,
                "economic_scale_signature": signature,
            }
        )
    if missing_signature:
        systems[0].pop("economic_scale_signature")
    return [
        _topic("places", places),
        _topic("economy_law", systems),
    ]


def test_profile_graph_injects_scoped_economic_scale_contract() -> None:
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    graph = build_profile_topic_graph(profile, campaign_template="classic_fantasy")
    places = graph.node_map()["places"]
    economy = graph.node_map()["economy_law"]
    place_fields = {
        str(row.get("field_id")): row
        for row in places.metadata["field_definitions"]
    }
    economy_fields = {
        str(row.get("field_id")): row
        for row in economy.metadata["field_definitions"]
    }

    assert place_fields["economic_scale_signature"]["required"] is True
    assert economy_fields["economic_scale_signature"]["required"] is True
    assert economy_fields["affected_place_ids"]["required"] is True
    assert places.metadata["economic_scale_contract"]["expected_scope"] == (
        "place_population"
    )
    assert economy.metadata["economic_scale_contract"]["expected_scope"] == (
        "service_system"
    )
    assert economy.metadata["economic_scale_contract"][
        "signature_components"
    ] == list(economic_scale_components())
    assert graph.metadata["economic_scale_contract"]["domain_ids"] == [
        "economy_law",
        "places",
    ]


def test_launch_graph_retains_economic_scale_domains() -> None:
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    graph = build_profile_topic_graph(profile, campaign_template="classic_fantasy")
    launch = build_profile_launch_topic_graph(graph, profile)

    assert {"places", "economy_law"}.issubset(launch.node_map())
    assert launch.node_map()["places"].required_before_launch is True
    assert launch.node_map()["economy_law"].required_before_launch is True


def test_deterministic_generation_builds_valid_scale_portfolio() -> None:
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    graph = build_profile_topic_graph(profile, campaign_template="classic_fantasy")
    regions = GeneratedTopic(
        topic_id="regions",
        entities=tuple({"id": f"ent:region:{index}"} for index in range(1, 5)),
    )
    places = generate_deterministic_profile_topic(
        graph.node_map()["places"],
        campaign_context={"world_brief": {"title": "Cinder March"}},
        dependency_topics={"regions": regions},
    )
    groups = GeneratedTopic(
        topic_id="groups",
        entities=tuple({"id": f"ent:group:{index}"} for index in range(1, 7)),
    )
    technology = GeneratedTopic(
        topic_id="technology_augmentations",
        entities=tuple(
            {"id": f"ent:technology:{index}"} for index in range(1, 7)
        ),
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
        {"topic_id": "economy_law", "candidate": economy.as_dict()},
    ]

    report = economic_scale_report(rows, graph.as_dict())

    assert report["passed"] is True
    assert report["checks"]["scale_scopes"] == [
        "place_population",
        "service_system",
    ]
    assert report["checks"]["valid_signature_count"] == report["checks"][
        "scale_entity_count"
    ]
    assert all(entity["affected_place_ids"] for entity in economy.entities)


def test_representative_economic_scale_portfolio_passes() -> None:
    report = economic_scale_report(_portfolio_rows(), _graph())

    assert report["passed"] is True
    assert report["checks"]["scale_entity_count"] == 7
    assert report["checks"]["scale_scopes"] == [
        "place_population",
        "service_system",
    ]


def test_missing_signature_and_scope_mismatch_are_blocking() -> None:
    missing = economic_scale_issues(
        _portfolio_rows(missing_signature=True),
        _graph(),
    )
    mismatch = economic_scale_issues(
        _portfolio_rows(scope_mismatch=True),
        _graph(),
    )

    assert any(issue.code == "economic_scale_signature_required" for issue in missing)
    assert any(issue.code == "economic_scale_scope_mismatch" for issue in mismatch)


def test_unknown_and_unbounded_bands_are_blocking() -> None:
    unknown = economic_scale_issues(
        _portfolio_rows(unknown_band=True),
        _graph(),
    )
    unbounded = economic_scale_issues(
        _portfolio_rows(unbounded_throughput=True),
        _graph(),
    )

    assert any(issue.code == "economic_scale_band_unknown" for issue in unknown)
    assert any(issue.code == "unbounded_economic_scale" for issue in unbounded)


def test_population_workforce_reach_and_throughput_must_agree() -> None:
    workforce = economic_scale_issues(
        _portfolio_rows(workforce_exceeds_population=True),
        _graph(),
    )
    reach = economic_scale_issues(
        _portfolio_rows(reach_exceeds_population=True),
        _graph(),
    )
    throughput = economic_scale_issues(
        _portfolio_rows(throughput_exceeds_workforce=True),
        _graph(),
    )

    assert any(
        issue.code == "economic_workforce_exceeds_population_scale"
        for issue in workforce
    )
    assert any(
        issue.code == "economic_service_reach_exceeds_population_scale"
        for issue in reach
    )
    assert any(
        issue.code == "economic_throughput_exceeds_workforce_capacity"
        for issue in throughput
    )


def test_scarcity_requires_matching_reserve_horizon() -> None:
    issues = economic_scale_issues(
        _portfolio_rows(scarcity_reserve_mismatch=True),
        _graph(),
    )

    assert any(
        issue.code == "economic_scarcity_not_supported_by_reserve"
        for issue in issues
    )


def test_service_systems_require_grounded_coverage() -> None:
    missing = economic_scale_issues(
        _portfolio_rows(missing_coverage=True),
        _graph(),
    )
    narrow = economic_scale_issues(
        _portfolio_rows(narrow_coverage=True),
        _graph(),
    )

    assert any(issue.code == "economic_service_coverage_required" for issue in missing)
    assert any(
        issue.code == "economic_service_coverage_below_reach_band"
        for issue in narrow
    )


def test_duplicate_complete_scale_signature_is_blocking() -> None:
    issues = economic_scale_issues(
        _portfolio_rows(duplicate_signature=True),
        _graph(),
    )

    issue = next(
        issue for issue in issues if issue.code == "duplicate_economic_scale_signature"
    )
    assert issue.evidence["entity_ids"] == [
        "ent:economy:1",
        "ent:economy:2",
    ]


def test_scale_portfolio_requires_band_diversity() -> None:
    issues = economic_scale_issues(
        _portfolio_rows(uniform_components=True),
        _graph(),
    )

    components = {
        issue.evidence["component"]
        for issue in issues
        if issue.code == "economic_scale_portfolio_too_uniform"
    }
    assert components == {
        "served_population_band",
        "throughput_band",
        "price_basis",
        "scarcity_level",
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

    with pytest.raises(EconomicScaleCompilationError):
        generation_compilation.compile_world_generation_certified_artifact(
            run={"run_id": "run:1", "graph": _graph()},
            world={"id": "world:1"},
            topic_rows=_portfolio_rows(workforce_exceeds_population=True),
            revision=1,
        )

    assert called is False


def test_diagnostic_compilation_retains_economic_scale_report(
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

    report = artifact.certification["economic_scale"]
    assert report["passed"] is False
    assert artifact.certification["launch_ready"] is False
    assert "economic_scale" in artifact.certification["missing_requirements"]


def test_publication_transaction_surfaces_economic_scale_failure() -> None:
    report = publication_transaction_report(
        {
            "run_id": "run:1",
            "world_id": "world:1",
            "status": "review",
            "progress": {"publication_blocked": False},
        },
        {
            "launch_ready": False,
            "missing_requirements": ["economic_scale"],
            "economic_scale": {
                "passed": False,
                "issues": [
                    {"code": "economic_throughput_exceeds_workforce_capacity"}
                ],
            },
        },
    )

    assert report["publishable"] is False
    assert "economic_scale" in report["failed_reports"]
