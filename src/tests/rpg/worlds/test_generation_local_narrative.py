from __future__ import annotations

import pytest

from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.session.genesis.world_forge_local_narrative import (
    deterministic_local_narrative_signature,
    local_narrative_components,
)
from app.rpg.session.genesis.world_forge_profile_deterministic import generate_deterministic_profile_topic
from app.rpg.session.genesis.world_forge_profile_generation import default_profile_registry
from app.rpg.session.genesis.world_forge_profile_graph import build_profile_topic_graph
from app.rpg.worlds import generation_compilation
from app.rpg.worlds.generation_local_narrative import (
    LocalNarrativeCompilationError,
    local_narrative_issues,
    local_narrative_report,
)
from app.rpg.worlds.generation_publication_transaction import publication_transaction_report


def _graph() -> dict:
    fields = [
        {"field_id": "local_place_ids", "value_type": "entity_ref_list", "required": True, "allowed_target_domains": ["places"]},
        {"field_id": "local_pressure_ids", "value_type": "entity_ref_list", "required": True, "allowed_target_domains": ["pressures"]},
        {"field_id": "local_actor_ids", "value_type": "entity_ref_list", "required": True, "allowed_target_domains": ["actors"]},
        {"field_id": "local_group_ids", "value_type": "entity_ref_list", "required": True, "allowed_target_domains": ["groups"]},
        {"field_id": "local_evidence_source_ids", "value_type": "entity_ref_list", "required": True, "allowed_target_domains": ["places", "pressures", "actors", "groups"]},
        {"field_id": "local_narrative_signature", "value_type": "structured_object", "required": True},
    ]
    return {"nodes": [{"topic_id": "opening_threads", "metadata": {"field_definitions": fields}}]}


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


def _rows() -> list[dict]:
    places = [{"id": f"ent:place:{index}"} for index in range(1, 6)]
    actors = [{"id": f"ent:actor:{index}", "location_id": f"ent:place:{index}"} for index in range(1, 6)]
    pressures = [{"id": f"ent:pressure:{index}"} for index in range(1, 6)]
    groups = [
        {
            "id": f"ent:group:{index}",
            "information_place_ids": [f"ent:place:{index}", f"ent:place:{(index % 5) + 1}"],
        }
        for index in range(1, 6)
    ]
    opportunities = []
    for index in range(4):
        current = index + 1
        next_value = (current % 5) + 1
        opportunities.append(
            {
                "id": f"ent:opening:{current}",
                "local_place_ids": [f"ent:place:{current}", f"ent:place:{next_value}"],
                "local_pressure_ids": [f"ent:pressure:{current}"],
                "local_actor_ids": [f"ent:actor:{current}", f"ent:actor:{next_value}"],
                "local_group_ids": [f"ent:group:{current}"],
                "local_evidence_source_ids": [f"ent:place:{current}"],
                "local_narrative_signature": deterministic_local_narrative_signature(index),
            }
        )
    return [
        _topic("places", places),
        _topic("actors", actors),
        _topic("pressures", pressures),
        _topic("groups", groups),
        _topic("opening_threads", opportunities),
    ]


def test_profile_graph_injects_local_narrative_contract() -> None:
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    graph = build_profile_topic_graph(profile, campaign_template="classic_fantasy")

    for topic_id in ("quests", "encounter_seeds", "opening_threads"):
        fields = {
            str(row.get("field_id")): row
            for row in graph.node_map()[topic_id].metadata["field_definitions"]
        }
        assert fields["local_place_ids"]["required"] is True
        assert fields["local_pressure_ids"]["allowed_target_domains"] == ["pressures"]
        assert fields["local_narrative_signature"]["required"] is True
    assert list(local_narrative_components()) == [
        "discovery_channel", "evidence_form", "urgency_band", "expiry_window",
        "consequence_scope", "entry_mode", "information_scope", "failure_visibility",
    ]


def test_deterministic_generation_builds_locally_grounded_opportunities() -> None:
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    graph = build_profile_topic_graph(profile, campaign_template="classic_fantasy")
    node = graph.node_map()["opening_threads"]
    places = tuple({"id": f"ent:place:{index}"} for index in range(1, 9))
    actors = tuple({"id": f"ent:actor:{index}", "location_id": f"ent:place:{index}"} for index in range(1, 9))
    pressures = tuple({"id": f"ent:pressure:{index}"} for index in range(1, 9))
    groups = tuple({"id": f"ent:group:{index}", "information_place_ids": [f"ent:place:{index}", f"ent:place:{(index % 8) + 1}"]} for index in range(1, 9))
    dependencies = {
        "places": GeneratedTopic(topic_id="places", entities=places),
        "actors": GeneratedTopic(topic_id="actors", entities=actors),
        "pressures": GeneratedTopic(topic_id="pressures", entities=pressures),
        "groups": GeneratedTopic(topic_id="groups", entities=groups),
    }
    generated = generate_deterministic_profile_topic(
        node,
        campaign_context={"world_brief": {"title": "Cinder March"}},
        dependency_topics=dependencies,
    )
    rows = [
        _topic("places", list(places)),
        _topic("actors", list(actors)),
        _topic("pressures", list(pressures)),
        _topic("groups", list(groups)),
        {"topic_id": "opening_threads", "candidate": generated.as_dict()},
    ]

    report = local_narrative_report(rows, graph.as_dict())

    assert report["passed"] is True
    assert report["checks"]["opportunity_count"] == len(generated.entities)


def test_missing_invalid_and_remote_evidence_references_are_blocking() -> None:
    rows = _rows()
    rows[-1]["candidate"]["entities"][0]["local_actor_ids"] = []
    missing = local_narrative_issues(rows, _graph())
    rows = _rows()
    rows[-1]["candidate"]["entities"][0]["local_place_ids"] = ["ent:place:missing"]
    invalid = local_narrative_issues(rows, _graph())
    rows = _rows()
    rows[-1]["candidate"]["entities"][0]["local_evidence_source_ids"] = ["ent:group:5"]
    remote = local_narrative_issues(rows, _graph())

    assert any(row.code == "local_narrative_reference_required" for row in missing)
    assert any(row.code == "local_narrative_reference_invalid" for row in invalid)
    assert any(row.code == "local_narrative_evidence_not_local" for row in remote)


def test_omniscient_and_faction_reach_contradictions_are_blocking() -> None:
    rows = _rows()
    rows[-1]["candidate"]["entities"][0]["local_narrative_signature"]["information_scope"] = "global"
    omniscient = local_narrative_issues(rows, _graph())
    rows = _rows()
    opportunity = rows[-1]["candidate"]["entities"][0]
    opportunity["local_narrative_signature"]["information_scope"] = "faction_reach"
    opportunity["local_place_ids"] = ["ent:place:4"]
    opportunity["local_actor_ids"] = ["ent:actor:4"]
    opportunity["local_evidence_source_ids"] = ["ent:place:4"]
    opportunity["local_group_ids"] = ["ent:group:1"]
    contradiction = local_narrative_issues(rows, _graph())

    assert any(row.code == "local_narrative_component_unbounded:information_scope" for row in omniscient)
    assert any(row.code == "local_narrative_exceeds_faction_information_reach" for row in contradiction)


def test_duplicate_and_single_pressure_portfolios_are_blocking() -> None:
    rows = _rows()
    first = rows[-1]["candidate"]["entities"][0]
    rows[-1]["candidate"]["entities"][1] = {**first, "id": "ent:opening:2"}
    duplicate = local_narrative_issues(rows, _graph())
    rows = _rows()
    for opportunity in rows[-1]["candidate"]["entities"]:
        opportunity["local_pressure_ids"] = ["ent:pressure:1"]
    concentrated = local_narrative_issues(rows, _graph())

    assert any(row.code == "duplicate_local_narrative_opportunity" for row in duplicate)
    assert any(row.code == "local_narrative_pressure_concentration_high" for row in concentrated)


def test_certified_compilation_fails_before_legacy_compiler(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _rows()
    rows[-1]["candidate"]["entities"][0].pop("local_narrative_signature")
    called = False

    def legacy(**_kwargs: object) -> object:
        nonlocal called
        called = True
        raise AssertionError("legacy compiler should not run")

    monkeypatch.setattr(generation_compilation, "compile_world_generation_publication", legacy)
    monkeypatch.setattr(generation_compilation, "_reports", lambda values, graph: {"local_narrative": local_narrative_report(values, graph)})
    monkeypatch.setattr(generation_compilation, "_graph_audits", lambda: (("local_narrative", local_narrative_report, generation_compilation.extension_audits()[-1][2]),))
    monkeypatch.setattr(generation_compilation, "require_unique_canon_identifiers", lambda _rows: None)
    monkeypatch.setattr(generation_compilation, "require_resolved_objective_named_claims", lambda _rows: None)

    with pytest.raises(LocalNarrativeCompilationError):
        generation_compilation.compile_world_generation_artifact(
            mode="certified_release",
            run={"graph": _graph()},
            world={},
            topic_rows=rows,
            revision=1,
        )
    assert called is False


def test_transaction_discovers_failed_local_narrative_report() -> None:
    report = publication_transaction_report(
        {"run_id": "run:1", "world_id": "world:1", "status": "review", "progress": {}},
        {"launch_ready": False, "missing_requirements": ["local_narrative"], "local_narrative": {"passed": False, "issues": []}},
    )

    assert report["publishable"] is False
    assert "local_narrative" in report["failed_reports"]
