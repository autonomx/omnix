from __future__ import annotations

import pytest

from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.session.genesis.world_forge_profile_deterministic import generate_deterministic_profile_topic
from app.rpg.session.genesis.world_forge_profile_generation import default_profile_registry
from app.rpg.session.genesis.world_forge_profile_graph import build_profile_topic_graph
from app.rpg.session.genesis.world_forge_route_effects import deterministic_route_effect_signature, route_effect_components
from app.rpg.worlds import generation_compilation
from app.rpg.worlds.generation_route_effects import RouteEffectCompilationError, route_effect_issues, route_effect_report
from app.rpg.worlds.generation_publication_transaction import publication_transaction_report


def _graph() -> dict:
    return {"nodes": [{"topic_id": "places", "metadata": {"field_definitions": [
        {"field_id": "connected_place_ids", "value_type": "entity_ref_list", "required": True},
        {"field_id": "route_effects", "value_type": "structured_object", "required": True},
    ]}}]}


def _topic(entities: list[dict]) -> dict:
    return {"topic_id": "places", "candidate": {"topic_id": "places", "documents": [], "entities": entities, "facts": [], "relationships": [], "knowledge_rules": [], "story_threads": [], "provenance": {}}}


def _rows() -> list[dict]:
    places = []
    for index in range(4):
        endpoint = f"ent:place:{((index + 1) % 4) + 1}"
        places.append({
            "id": f"ent:place:{index + 1}",
            "connected_place_ids": [endpoint],
            "local_market_signature": {"shock_sensitivity": "moderate"},
            "route_effects": {endpoint: deterministic_route_effect_signature(index)},
        })
    return [_topic(places)]


def test_profile_graph_requires_route_effect_maps() -> None:
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    graph = build_profile_topic_graph(profile, campaign_template="classic_fantasy")
    fields = {str(row.get("field_id")): row for row in graph.node_map()["places"].metadata["field_definitions"]}

    assert fields["route_effects"]["required"] is True
    assert list(route_effect_components()) == [
        "travel_cost_band", "time_variance", "hazard_level", "supply_effect",
        "price_effect", "information_delay", "closure_recovery",
    ]


def test_deterministic_routes_align_with_connected_endpoints() -> None:
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    graph = build_profile_topic_graph(profile, campaign_template="classic_fantasy", depth="epic")
    node = graph.node_map()["places"]
    dependencies = {domain_id: GeneratedTopic(topic_id=domain_id, entities=tuple({"id": f"ent:{domain_id}:{index}"} for index in range(1, 20))) for domain_id in node.dependencies}
    places = generate_deterministic_profile_topic(node, campaign_context={"world_brief": {"title": "Cinder March"}}, dependency_topics=dependencies)
    report = route_effect_report([{"topic_id": "places", "candidate": places.as_dict()}], graph.as_dict())

    assert report["passed"] is True
    assert all(set(entity["route_effects"]) == set(entity["connected_place_ids"]) for entity in places.entities)


def test_missing_and_invented_endpoint_effects_are_blocking() -> None:
    rows = _rows(); place = rows[0]["candidate"]["entities"][0]; place["route_effects"] = {}
    missing = route_effect_issues(rows, _graph())
    rows = _rows(); rows[0]["candidate"]["entities"][0]["route_effects"]["ent:place:missing"] = deterministic_route_effect_signature(9)
    extra = route_effect_issues(rows, _graph())

    assert any(row.code == "route_effect_endpoint_missing" for row in missing)
    assert any(row.code == "route_effect_endpoint_not_connected" for row in extra)


def test_unbounded_route_and_route_sensitive_market_without_effect_are_blocking() -> None:
    rows = _rows(); place = rows[0]["candidate"]["entities"][0]; endpoint = place["connected_place_ids"][0]
    place["route_effects"][endpoint]["travel_cost_band"] = "zero"
    unbounded = route_effect_issues(rows, _graph())
    rows = _rows(); place = rows[0]["candidate"]["entities"][0]; endpoint = place["connected_place_ids"][0]
    place["local_market_signature"] = {"shock_sensitivity": "route_sensitive"}
    place["route_effects"][endpoint]["supply_effect"] = "neutral_supply"
    insensitive = route_effect_issues(rows, _graph())

    assert any(row.code == "route_effect_component_unbounded:travel_cost_band" for row in unbounded)
    assert any(row.code == "route_sensitive_market_without_route_effect" for row in insensitive)


def test_route_effect_portfolio_requires_diversity() -> None:
    rows = _rows()
    for place in rows[0]["candidate"]["entities"]:
        endpoint = place["connected_place_ids"][0]
        place["route_effects"][endpoint] = {**place["route_effects"][endpoint], "hazard_level": "low", "supply_effect": "neutral_supply", "information_delay": "one_day"}
    issues = route_effect_issues(rows, _graph())

    assert {row.evidence["component"] for row in issues if row.code == "route_effect_component_uniform"} == {"hazard_level", "supply_effect", "information_delay"}


def test_certified_compilation_fails_before_legacy_compiler(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _rows(); rows[0]["candidate"]["entities"][0].pop("route_effects")
    called = False
    def legacy(**_kwargs: object) -> object:
        nonlocal called; called = True; raise AssertionError("legacy compiler should not run")
    monkeypatch.setattr(generation_compilation, "compile_world_generation_publication", legacy)
    monkeypatch.setattr(generation_compilation, "_reports", lambda values, graph: {"route_effects": route_effect_report(values, graph)})
    monkeypatch.setattr(generation_compilation, "_graph_audits", lambda: (("route_effects", route_effect_report, generation_compilation.extension_audits()[0][2]),))
    monkeypatch.setattr(generation_compilation, "require_unique_canon_identifiers", lambda _rows: None)
    monkeypatch.setattr(generation_compilation, "require_resolved_objective_named_claims", lambda _rows: None)
    with pytest.raises(RouteEffectCompilationError):
        generation_compilation.compile_world_generation_artifact(mode="certified_release", run={"graph": _graph()}, world={}, topic_rows=rows, revision=1)
    assert called is False


def test_transaction_discovers_failed_route_report_without_allowlist() -> None:
    report = publication_transaction_report(
        {"run_id": "run:1", "world_id": "world:1", "status": "review", "progress": {}},
        {"launch_ready": False, "missing_requirements": ["route_effects"], "route_effects": {"passed": False, "issues": []}},
    )
    assert report["publishable"] is False
    assert "route_effects" in report["failed_reports"]
