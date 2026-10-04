from __future__ import annotations

import pytest

from app.rpg.session.genesis.world_forge_countervailing_powers import (
    countervailing_power_components,
    deterministic_countervailing_power_signature,
)
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.session.genesis.world_forge_profile_deterministic import generate_deterministic_profile_topic
from app.rpg.session.genesis.world_forge_profile_generation import default_profile_registry
from app.rpg.session.genesis.world_forge_profile_graph import build_profile_launch_topic_graph, build_profile_topic_graph
from app.rpg.worlds import generation_compilation
from app.rpg.worlds.generation_countervailing_powers import (
    CountervailingPowerCompilationError,
    countervailing_power_issues,
    countervailing_power_report,
)
from app.rpg.worlds.generation_publication_transaction import publication_transaction_report


def _graph() -> dict:
    return {
        "metadata": {},
        "nodes": [{
            "topic_id": "groups",
            "metadata": {"field_definitions": [
                {"field_id": "constrained_by_group_ids", "value_type": "entity_ref_list", "required": True, "allowed_target_domains": ["groups"]},
                {"field_id": "countervailing_power_signature", "value_type": "structured_object", "required": True},
            ]},
        }],
    }


def _topic(entities: list[dict]) -> dict:
    return {"topic_id": "groups", "candidate": {"topic_id": "groups", "documents": [], "entities": entities, "facts": [], "relationships": [], "knowledge_rules": [], "story_threads": [], "provenance": {}}}


def _rows(*, duplicate: bool = False) -> list[dict]:
    groups = []
    for index in range(4):
        groups.append({
            "id": f"ent:group:{index + 1}",
            "constrained_by_group_ids": [f"ent:group:{((index + 1) % 4) + 1}"],
            "countervailing_power_signature": deterministic_countervailing_power_signature(0 if duplicate and index == 1 else index),
        })
    return [_topic(groups)]


def test_profile_graph_injects_countervailing_power_contract() -> None:
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    graph = build_profile_topic_graph(profile, campaign_template="classic_fantasy")
    groups = graph.node_map()["groups"]
    fields = {str(row.get("field_id")): row for row in groups.metadata["field_definitions"]}

    assert fields["constrained_by_group_ids"]["required"] is True
    assert fields["constrained_by_group_ids"]["allowed_target_domains"] == ["groups"]
    assert fields["countervailing_power_signature"]["required"] is True
    assert set(countervailing_power_components()) == {
        "authority_source", "constraint_mechanism", "leverage_type", "accountability_channel",
        "mobilization_speed", "territorial_reach", "vulnerability", "failure_condition",
    }


def test_launch_graph_retains_countervailing_groups() -> None:
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    graph = build_profile_topic_graph(profile, campaign_template="classic_fantasy")
    launch = build_profile_launch_topic_graph(graph, profile)

    assert "groups" in launch.node_map()
    assert launch.node_map()["groups"].required_before_launch is True


def test_deterministic_generation_builds_valid_countervailing_portfolio() -> None:
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    graph = build_profile_topic_graph(profile, campaign_template="classic_fantasy")
    node = graph.node_map()["groups"]
    dependencies = {
        domain_id: GeneratedTopic(topic_id=domain_id, entities=tuple({"id": f"ent:{domain_id}:{index}"} for index in range(1, 9)))
        for domain_id in node.dependencies
    }
    groups = generate_deterministic_profile_topic(node, campaign_context={"world_brief": {"title": "Cinder March"}}, dependency_topics=dependencies)
    report = countervailing_power_report([{"topic_id": "groups", "candidate": groups.as_dict()}], graph.as_dict())

    assert report["passed"] is True
    assert report["checks"]["group_count"] == len(groups.entities)
    assert all(entity["constrained_by_group_ids"] for entity in groups.entities)


def test_missing_self_and_unknown_constraints_are_blocking() -> None:
    rows = _rows(); rows[0]["candidate"]["entities"][0]["constrained_by_group_ids"] = []
    missing = countervailing_power_issues(rows, _graph())
    rows = _rows(); rows[0]["candidate"]["entities"][0]["constrained_by_group_ids"] = ["ent:group:1", "ent:group:missing"]
    invalid = countervailing_power_issues(rows, _graph())

    assert any(row.code == "countervailing_constraint_required" for row in missing)
    assert any(row.code == "countervailing_constraint_reference_invalid" for row in invalid)


def test_duplicate_and_disconnected_power_profiles_are_blocking() -> None:
    duplicate = countervailing_power_issues(_rows(duplicate=True), _graph())
    rows = _rows()
    groups = rows[0]["candidate"]["entities"]
    groups[0]["constrained_by_group_ids"] = ["ent:group:2"]
    groups[1]["constrained_by_group_ids"] = ["ent:group:1"]
    groups[2]["constrained_by_group_ids"] = ["ent:group:4"]
    groups[3]["constrained_by_group_ids"] = ["ent:group:3"]
    disconnected = countervailing_power_issues(rows, _graph())

    assert any(row.code == "duplicate_countervailing_power_signature" for row in duplicate)
    assert any(row.code == "countervailing_power_graph_disconnected" for row in disconnected)


def test_constraint_uniformity_is_blocking() -> None:
    rows = _rows()
    for group in rows[0]["candidate"]["entities"]:
        group["countervailing_power_signature"] = {
            **group["countervailing_power_signature"],
            "constraint_mechanism": "budget_veto",
            "leverage_type": "credit_access",
            "vulnerability": "funding_shortfall",
        }
    uniform = countervailing_power_issues(rows, _graph())

    assert {row.evidence["component"] for row in uniform if row.code == "countervailing_power_component_uniform"} == {"constraint_mechanism", "leverage_type", "vulnerability"}


def test_certified_compilation_fails_before_legacy_compiler(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _rows(); rows[0]["candidate"]["entities"][0].pop("countervailing_power_signature")
    graph = _graph(); called = False
    def legacy(**_kwargs: object) -> object:
        nonlocal called; called = True; raise AssertionError("legacy compiler should not run")
    monkeypatch.setattr(generation_compilation, "compile_world_generation_publication", legacy)
    monkeypatch.setattr(generation_compilation, "_reports", lambda values, configured: {"countervailing_powers": countervailing_power_report(values, configured)})
    monkeypatch.setattr(generation_compilation, "_graph_audits", lambda: (("countervailing_powers", countervailing_power_report, generation_compilation.require_valid_countervailing_powers),))
    monkeypatch.setattr(generation_compilation, "require_unique_canon_identifiers", lambda _rows: None)
    monkeypatch.setattr(generation_compilation, "require_resolved_objective_named_claims", lambda _rows: None)
    with pytest.raises(CountervailingPowerCompilationError):
        generation_compilation.compile_world_generation_artifact(mode="certified_release", run={"graph": graph}, world={}, topic_rows=rows, revision=1)
    assert called is False


def test_transaction_reports_failed_countervailing_power_audit() -> None:
    report = publication_transaction_report(
        {"run_id": "run:1", "world_id": "world:1", "status": "review", "progress": {}},
        {"launch_ready": False, "missing_requirements": ["countervailing_powers"], "countervailing_powers": {"passed": False, "issues": []}},
    )
    assert report["publishable"] is False
    assert "countervailing_powers" in report["failed_reports"]
