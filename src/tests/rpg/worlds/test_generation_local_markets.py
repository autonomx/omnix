from __future__ import annotations

import pytest

from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.session.genesis.world_forge_local_markets import (
    deterministic_local_market_signature,
    local_market_components,
)
from app.rpg.session.genesis.world_forge_profile_deterministic import generate_deterministic_profile_topic
from app.rpg.session.genesis.world_forge_profile_generation import default_profile_registry
from app.rpg.session.genesis.world_forge_profile_graph import build_profile_launch_topic_graph, build_profile_topic_graph
from app.rpg.worlds import generation_compilation
from app.rpg.worlds.generation_local_markets import (
    LocalMarketCompilationError,
    local_market_issues,
    local_market_report,
)
from app.rpg.worlds.generation_publication_transaction import publication_transaction_report


def _graph() -> dict:
    return {"metadata": {}, "nodes": [{"topic_id": "places", "metadata": {"field_definitions": [{"field_id": "local_market_signature", "value_type": "structured_object", "required": True}]}}]}


def _topic(entities: list[dict]) -> dict:
    return {"topic_id": "places", "candidate": {"topic_id": "places", "documents": [], "entities": entities, "facts": [], "relationships": [], "knowledge_rules": [], "story_threads": [], "provenance": {}}}


def _rows(*, duplicate: bool = False) -> list[dict]:
    places = []
    for index in range(5):
        places.append({
            "id": f"ent:place:{index + 1}",
            "economic_scale_signature": {"scarcity_level": "constrained"},
            "local_market_signature": deterministic_local_market_signature(0 if duplicate and index == 1 else index),
        })
    return [_topic(places)]


def test_profile_graph_injects_local_market_contract() -> None:
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    graph = build_profile_topic_graph(profile, campaign_template="classic_fantasy")
    places = graph.node_map()["places"]
    fields = {str(row.get("field_id")): row for row in places.metadata["field_definitions"]}

    assert fields["local_market_signature"]["required"] is True
    assert list(local_market_components()) == [
        "market_scope", "demand_profile", "supply_reliability", "price_level",
        "credit_access", "informal_share", "enforcement_level",
        "shock_sensitivity", "recovery_horizon",
    ]


def test_launch_graph_retains_local_market_places() -> None:
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    graph = build_profile_topic_graph(profile, campaign_template="classic_fantasy")
    launch = build_profile_launch_topic_graph(graph, profile)

    assert "places" in launch.node_map()
    assert launch.node_map()["places"].required_before_launch is True


def test_deterministic_generation_builds_valid_local_markets() -> None:
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    graph = build_profile_topic_graph(profile, campaign_template="classic_fantasy", depth="epic")
    node = graph.node_map()["places"]
    dependencies = {domain_id: GeneratedTopic(topic_id=domain_id, entities=tuple({"id": f"ent:{domain_id}:{index}"} for index in range(1, 20))) for domain_id in node.dependencies}
    places = generate_deterministic_profile_topic(node, campaign_context={"world_brief": {"title": "Cinder March"}}, dependency_topics=dependencies)
    report = local_market_report([{"topic_id": "places", "candidate": places.as_dict()}], graph.as_dict())

    assert report["passed"] is True
    assert report["checks"]["place_count"] == len(places.entities)


def test_missing_unbounded_and_duplicate_markets_are_blocking() -> None:
    rows = _rows(); rows[0]["candidate"]["entities"][0].pop("local_market_signature")
    missing = local_market_issues(rows, _graph())
    rows = _rows(); rows[0]["candidate"]["entities"][0]["local_market_signature"]["market_scope"] = "global"
    unbounded = local_market_issues(rows, _graph())
    duplicate = local_market_issues(_rows(duplicate=True), _graph())

    assert any(row.code == "local_market_signature_required" for row in missing)
    assert any(row.code == "local_market_component_unbounded:market_scope" for row in unbounded)
    assert any(row.code == "duplicate_local_market_signature" for row in duplicate)


def test_local_market_must_agree_with_scarcity() -> None:
    rows = _rows(); place = rows[0]["candidate"]["entities"][0]
    place["economic_scale_signature"] = {"scarcity_level": "critical"}
    place["local_market_signature"] = {**place["local_market_signature"], "supply_reliability": "robust", "price_level": "stable"}
    issues = local_market_issues(rows, _graph())

    assert any(row.code == "local_market_supply_conflicts_with_scarcity" for row in issues)
    assert any(row.code == "local_market_price_conflicts_with_scarcity" for row in issues)


def test_market_portfolio_requires_local_diversity() -> None:
    rows = _rows()
    for place in rows[0]["candidate"]["entities"]:
        place["local_market_signature"] = {**place["local_market_signature"], "supply_reliability": "seasonal", "price_level": "elevated", "shock_sensitivity": "route_sensitive"}
    issues = local_market_issues(rows, _graph())

    assert {row.evidence["component"] for row in issues if row.code == "local_market_component_uniform"} == {"supply_reliability", "price_level", "shock_sensitivity"}


def test_certified_compilation_fails_before_legacy_compiler(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _rows(); rows[0]["candidate"]["entities"][0].pop("local_market_signature")
    called = False
    def legacy(**_kwargs: object) -> object:
        nonlocal called; called = True; raise AssertionError("legacy compiler should not run")
    monkeypatch.setattr(generation_compilation, "compile_world_generation_publication", legacy)
    monkeypatch.setattr(generation_compilation, "_reports", lambda values, graph: {"local_markets": local_market_report(values, graph)})
    monkeypatch.setattr(generation_compilation, "_graph_audits", lambda: (("local_markets", local_market_report, generation_compilation.require_valid_local_markets),))
    monkeypatch.setattr(generation_compilation, "require_unique_canon_identifiers", lambda _rows: None)
    monkeypatch.setattr(generation_compilation, "require_resolved_objective_named_claims", lambda _rows: None)
    with pytest.raises(LocalMarketCompilationError):
        generation_compilation.compile_world_generation_artifact(mode="certified_release", run={"graph": _graph()}, world={}, topic_rows=rows, revision=1)
    assert called is False


def test_transaction_reports_failed_local_markets() -> None:
    report = publication_transaction_report(
        {"run_id": "run:1", "world_id": "world:1", "status": "review", "progress": {}},
        {"launch_ready": False, "missing_requirements": ["local_markets"], "local_markets": {"passed": False, "issues": []}},
    )
    assert report["publishable"] is False
    assert "local_markets" in report["failed_reports"]
