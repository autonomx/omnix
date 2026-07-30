from __future__ import annotations

import pytest

from app.rpg.session.genesis.world_forge_actor_incentives import (
    actor_incentive_components,
    deterministic_actor_incentive_signature,
)
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.session.genesis.world_forge_profile_deterministic import (
    generate_deterministic_profile_topic,
)
from app.rpg.session.genesis.world_forge_profile_generation import (
    default_profile_registry,
)
from app.rpg.session.genesis.world_forge_profile_graph import (
    build_profile_topic_graph,
)
from app.rpg.worlds import generation_compilation
from app.rpg.worlds.generation_actor_portfolio import (
    ActorPortfolioCompilationError,
    actor_portfolio_issues,
    actor_portfolio_report,
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
            "actor_incentive_contract": {
                "schema_version": "rpg_world_actor_incentive_contract_v1",
                "domain_ids": ["actors"],
            }
        },
        "nodes": [
            {
                "topic_id": "groups",
                "metadata": {"field_definitions": []},
            },
            {
                "topic_id": "actors",
                "metadata": {
                    "actor_incentive_contract": {
                        "required": True,
                        "signature_field": "incentive_signature",
                    },
                    "field_definitions": [
                        {
                            "field_id": "incentive_signature",
                            "value_type": "structured_object",
                            "required": True,
                        },
                        {
                            "field_id": "group_ids",
                            "value_type": "entity_ref_list",
                            "allowed_target_domains": ["groups"],
                            "semantic_role": "member_of",
                        },
                    ],
                },
            },
            {
                "topic_id": "pressures",
                "metadata": {
                    "field_definitions": [
                        {
                            "field_id": "actor_ids",
                            "value_type": "entity_ref_list",
                            "allowed_target_domains": ["actors"],
                            "semantic_role": "pressures_actor",
                        }
                    ]
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
            "provenance": {"generator": "actor_portfolio_test"},
        },
    }


def _portfolio_rows(
    *,
    duplicate_signature: bool = False,
    malformed_signature: bool = False,
    uniform_social_components: bool = False,
    isolated_actor: bool = False,
) -> list[dict]:
    group_names = ("Cedar Compact", "Violet Assembly", "Harbour Union", "Glass Circle")
    actor_names = ("Mara Venn", "Ilan Rook", "Sera Quill", "Tomas Vale")
    pressure_names = ("Broken Truce", "Supply Vote", "Witness Clock", "Border Claim")
    groups = [
        {"id": f"ent:group:{index}", "name": name}
        for index, name in enumerate(group_names, start=1)
    ]
    actors = []
    for index, name in enumerate(actor_names):
        signature = deterministic_actor_incentive_signature(index)
        if duplicate_signature and index == 1:
            signature = deterministic_actor_incentive_signature(0)
        if uniform_social_components:
            signature = {
                **signature,
                "dependency_type": "institutional",
                "alliance_preference": "formal_alliance",
                "conflict_preference": "legal_pressure",
            }
        if malformed_signature and index == 0:
            signature = {"primary_motive": "security"}
        actors.append(
            {
                "id": f"ent:actor:{index + 1}",
                "name": name,
                "group_ids": [] if isolated_actor and index == 0 else [f"ent:group:{index + 1}"],
                "incentive_signature": signature,
            }
        )
    pressures = [
        {
            "id": f"ent:pressure:{index + 1}",
            "name": name,
            "actor_ids": [] if isolated_actor and index == 0 else [f"ent:actor:{index + 1}"],
        }
        for index, name in enumerate(pressure_names)
    ]
    return [
        _topic("groups", groups),
        _topic("actors", actors),
        _topic("pressures", pressures),
    ]


def test_profile_graph_injects_actor_incentive_contract() -> None:
    profile = default_profile_registry().resolve("cyberpunk")
    assert profile is not None
    graph = build_profile_topic_graph(profile, campaign_template="cyberpunk")
    actor_node = graph.node_map()["actors"]
    definitions = {
        str(row.get("field_id")): row
        for row in actor_node.metadata["field_definitions"]
    }

    assert definitions["incentive_signature"]["required"] is True
    assert actor_node.metadata["actor_incentive_contract"]["signature_components"] == list(
        actor_incentive_components()
    )
    assert graph.metadata["actor_incentive_contract"]["domain_ids"] == ["actors"]


def test_deterministic_actor_generation_emits_varied_signatures() -> None:
    profile = default_profile_registry().resolve("cyberpunk")
    assert profile is not None
    graph = build_profile_topic_graph(profile, campaign_template="cyberpunk")
    actor_node = graph.node_map()["actors"]
    dependencies = {
        "groups": GeneratedTopic(
            topic_id="groups",
            entities=tuple({"id": f"ent:group:{index}"} for index in range(1, 5)),
        ),
        "places": GeneratedTopic(
            topic_id="places",
            entities=tuple({"id": f"ent:place:{index}"} for index in range(1, 5)),
        ),
        "cultures": GeneratedTopic(
            topic_id="cultures",
            entities=tuple({"id": f"ent:culture:{index}"} for index in range(1, 5)),
        ),
    }

    topic = generate_deterministic_profile_topic(
        actor_node,
        campaign_context={"world_brief": {"title": "Neon Meridian", "genre": "cyberpunk"}},
        dependency_topics=dependencies,
    )

    signatures = [dict(entity["incentive_signature"]) for entity in topic.entities]
    assert all(set(signature) == set(actor_incentive_components()) for signature in signatures)
    assert len({tuple(sorted(signature.items())) for signature in signatures}) == len(signatures)


def test_diverse_actor_portfolio_passes() -> None:
    report = actor_portfolio_report(_portfolio_rows(), _graph())

    assert report["passed"] is True
    assert report["checks"]["actor_count"] == 4
    assert report["checks"]["valid_signature_count"] == 4
    assert report["checks"]["relationship_kind_count"] == 2
    assert report["checks"]["actors_without_relationships"] == []


def test_malformed_actor_signature_reports_missing_components() -> None:
    issues = actor_portfolio_issues(
        _portfolio_rows(malformed_signature=True),
        _graph(),
    )

    assert any(
        issue.code == "actor_incentive_component_required:scarce_need"
        and issue.actor_id == "ent:actor:1"
        for issue in issues
    )


def test_duplicate_complete_actor_signature_is_blocking() -> None:
    issues = actor_portfolio_issues(
        _portfolio_rows(duplicate_signature=True),
        _graph(),
    )

    issue = next(
        issue for issue in issues if issue.code == "duplicate_actor_incentive_signature"
    )
    assert issue.evidence["actor_ids"] == ["ent:actor:1", "ent:actor:2"]


def test_dependency_alliance_and_conflict_components_require_diversity() -> None:
    issues = actor_portfolio_issues(
        _portfolio_rows(uniform_social_components=True),
        _graph(),
    )

    components = {
        issue.evidence["component"]
        for issue in issues
        if issue.code == "actor_incentive_component_uniform"
    }
    assert components == {
        "dependency_type",
        "alliance_preference",
        "conflict_preference",
    }


def test_actor_without_non_spatial_relationship_is_blocking() -> None:
    issues = actor_portfolio_issues(
        _portfolio_rows(isolated_actor=True),
        _graph(),
    )

    assert any(
        issue.code == "actor_without_meaningful_relationship"
        and issue.actor_id == "ent:actor:1"
        for issue in issues
    )


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

    with pytest.raises(ActorPortfolioCompilationError):
        generation_compilation.compile_world_generation_certified_artifact(
            run={"run_id": "run:1", "graph": _graph()},
            world={"id": "world:1"},
            topic_rows=_portfolio_rows(duplicate_signature=True),
            revision=1,
        )

    assert called is False


def test_diagnostic_compilation_retains_actor_portfolio_report(
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
        topic_rows=_portfolio_rows(isolated_actor=True),
        revision=1,
    )

    report = artifact.certification["actor_portfolio"]
    assert report["passed"] is False
    assert artifact.certification["launch_ready"] is False
    assert "actor_portfolio" in artifact.certification["missing_requirements"]


def test_publication_transaction_surfaces_actor_portfolio_failure() -> None:
    report = publication_transaction_report(
        {
            "run_id": "run:1",
            "world_id": "world:1",
            "status": "review",
            "progress": {"publication_blocked": False},
        },
        {
            "launch_ready": False,
            "missing_requirements": ["actor_portfolio"],
            "actor_portfolio": {
                "passed": False,
                "issues": [{"code": "actor_without_meaningful_relationship"}],
            },
        },
    )

    assert report["publishable"] is False
    assert "actor_portfolio" in report["failed_reports"]
