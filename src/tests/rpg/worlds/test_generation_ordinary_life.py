from __future__ import annotations

import pytest

from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.session.genesis.world_forge_ordinary_life import (
    deterministic_ordinary_life_signature,
    ordinary_life_components,
)
from app.rpg.session.genesis.world_forge_profile_deterministic import generate_deterministic_profile_topic
from app.rpg.session.genesis.world_forge_profile_generation import default_profile_registry
from app.rpg.session.genesis.world_forge_profile_graph import build_profile_launch_topic_graph, build_profile_topic_graph
from app.rpg.worlds import generation_compilation
from app.rpg.worlds.generation_ordinary_life import (
    OrdinaryLifeCompilationError,
    ordinary_life_issues,
    ordinary_life_report,
)
from app.rpg.worlds.generation_publication_transaction import publication_transaction_report


def _graph() -> dict:
    return {
        "metadata": {"ordinary_life_contract": {"domain_ids": ["cultures"], "required_before_launch": True}},
        "nodes": [
            {"topic_id": "places", "metadata": {"field_definitions": []}},
            {
                "topic_id": "cultures",
                "metadata": {
                    "ordinary_life_contract": {
                        "required": True,
                        "place_field": "ordinary_life_place_ids",
                        "signature_field": "ordinary_life_signature",
                    },
                    "field_definitions": [],
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
            "provenance": {"generator": "ordinary_life_test"},
        },
    }


def _rows(*, duplicate: bool = False, abstract: bool = False) -> list[dict]:
    places = [{"id": f"ent:place:{index}"} for index in range(1, 5)]
    cultures = []
    for index in range(4):
        signature = deterministic_ordinary_life_signature(0 if duplicate and index == 1 else index)
        if abstract and index == 0:
            signature = {**signature, "work_pattern": "class_only"}
        cultures.append(
            {
                "id": f"ent:culture:{index + 1}",
                "ordinary_life_place_ids": [f"ent:place:{index + 1}"],
                "ordinary_life_signature": signature,
            }
        )
    return [_topic("places", places), _topic("cultures", cultures)]


def test_profile_graph_injects_ordinary_life_contract() -> None:
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    graph = build_profile_topic_graph(profile, campaign_template="classic_fantasy")
    culture = graph.node_map()["cultures"]
    fields = {str(row.get("field_id")): row for row in culture.metadata["field_definitions"]}

    assert fields["ordinary_life_place_ids"]["required"] is True
    assert fields["ordinary_life_place_ids"]["allowed_target_domains"] == ["places"]
    assert fields["ordinary_life_signature"]["required"] is True
    assert culture.metadata["ordinary_life_contract"]["signature_components"] == list(ordinary_life_components())
    assert graph.metadata["ordinary_life_contract"]["domain_ids"] == ["cultures"]


def test_launch_graph_retains_cultures_for_ordinary_life() -> None:
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    graph = build_profile_topic_graph(profile, campaign_template="classic_fantasy")
    launch = build_profile_launch_topic_graph(graph, profile)

    assert "cultures" in launch.node_map()
    assert launch.node_map()["cultures"].required_before_launch is True


def test_deterministic_cultures_build_valid_ordinary_life_portfolio() -> None:
    profile = default_profile_registry().resolve("fantasy")
    assert profile is not None
    graph = build_profile_topic_graph(profile, campaign_template="classic_fantasy")
    places = GeneratedTopic(topic_id="places", entities=tuple({"id": f"ent:place:{index}"} for index in range(1, 11)))
    histories = GeneratedTopic(topic_id="history_timeline", entities=tuple({"id": f"ent:event:{index}"} for index in range(1, 9)))
    regions = GeneratedTopic(topic_id="regions", entities=tuple({"id": f"ent:region:{index}"} for index in range(1, 9)))
    groups = GeneratedTopic(topic_id="groups", entities=tuple({"id": f"ent:group:{index}"} for index in range(1, 9)))
    cultures = generate_deterministic_profile_topic(
        graph.node_map()["cultures"],
        campaign_context={"world_brief": {"title": "Cinder March"}},
        dependency_topics={"history_timeline": histories, "regions": regions, "groups": groups, "places": places},
    )
    rows = [_topic("places", list(places.entities)), {"topic_id": "cultures", "candidate": cultures.as_dict()}]

    report = ordinary_life_report(rows, graph.as_dict())

    assert report["passed"] is True
    assert report["checks"]["culture_count"] == len(cultures.entities)
    assert all(entity["ordinary_life_place_ids"] for entity in cultures.entities)


def test_missing_and_unknown_place_grounding_are_blocking() -> None:
    rows = _rows()
    rows[1]["candidate"]["entities"][0]["ordinary_life_place_ids"] = []
    missing = ordinary_life_issues(rows, _graph())
    rows = _rows()
    rows[1]["candidate"]["entities"][0]["ordinary_life_place_ids"] = ["ent:place:missing"]
    unknown = ordinary_life_issues(rows, _graph())

    assert any(row.code == "ordinary_life_place_grounding_required" for row in missing)
    assert any(row.code == "ordinary_life_place_reference_invalid" for row in unknown)


def test_missing_abstract_and_duplicate_signatures_are_blocking() -> None:
    rows = _rows()
    rows[1]["candidate"]["entities"][0].pop("ordinary_life_signature")
    missing = ordinary_life_issues(rows, _graph())
    abstract = ordinary_life_issues(_rows(abstract=True), _graph())
    duplicate = ordinary_life_issues(_rows(duplicate=True), _graph())

    assert any(row.code == "ordinary_life_signature_required" for row in missing)
    assert any(row.code == "ordinary_life_component_abstract_only:work_pattern" for row in abstract)
    issue = next(row for row in duplicate if row.code == "duplicate_ordinary_life_signature")
    assert issue.evidence["culture_ids"] == ["ent:culture:1", "ent:culture:2"]


def test_uniform_daily_life_components_are_blocking() -> None:
    rows = _rows()
    for culture in rows[1]["candidate"]["entities"]:
        culture["ordinary_life_signature"] = {
            **culture["ordinary_life_signature"],
            "food_staple": "grain_and_stew",
            "work_pattern": "apprentice_workshops",
            "leisure_practice": "public_board_games",
            "care_practice": "mutual_aid_kitchen",
        }
    issues = ordinary_life_issues(rows, _graph())
    components = {row.evidence["component"] for row in issues if row.code == "ordinary_life_component_uniform"}

    assert components == {"food_staple", "work_pattern", "leisure_practice", "care_practice"}


def test_certified_compilation_fails_before_legacy_compiler(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _rows(abstract=True)
    graph = _graph()
    called = False

    def legacy(**_kwargs: object) -> object:
        nonlocal called
        called = True
        raise AssertionError("legacy compiler should not run")

    monkeypatch.setattr(generation_compilation, "compile_world_generation_publication", legacy)
    monkeypatch.setattr(generation_compilation, "_reports", lambda _rows, _graph: {"ordinary_life": ordinary_life_report(_rows, _graph)})
    monkeypatch.setattr(
        generation_compilation,
        "_graph_audits",
        lambda: (("ordinary_life", ordinary_life_report, generation_compilation.require_valid_ordinary_life),),
    )
    monkeypatch.setattr(generation_compilation, "require_unique_canon_identifiers", lambda _rows: None)
    monkeypatch.setattr(generation_compilation, "require_resolved_objective_named_claims", lambda _rows: None)

    with pytest.raises(OrdinaryLifeCompilationError):
        generation_compilation.compile_world_generation_artifact(
            mode="certified_release",
            run={"graph": graph},
            world={},
            topic_rows=rows,
            revision=1,
        )
    assert called is False


def test_transaction_reports_failed_ordinary_life() -> None:
    report = publication_transaction_report(
        {"run_id": "run:1", "world_id": "world:1", "status": "review", "progress": {}},
        {
            "launch_ready": False,
            "missing_requirements": ["ordinary_life"],
            "ordinary_life": {"passed": False, "issues": [{"code": "ordinary_life_signature_required"}]},
        },
    )

    assert report["publishable"] is False
    assert "ordinary_life" in report["failed_reports"]
