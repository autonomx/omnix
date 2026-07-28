from __future__ import annotations

import pytest

from app.rpg.session.genesis.world_forge_profile_deterministic import (
    generate_deterministic_profile_topic,
)
from app.rpg.session.genesis.world_forge_profile_generation import (
    resolve_or_generate_genre_profile,
)
from app.rpg.session.genesis.world_forge_profile_graph import (
    build_profile_topic_graph,
)
from app.rpg.worlds import generation_compilation
from app.rpg.worlds.generation_mission_portfolio import (
    MissionPortfolioCompilationError,
    mission_portfolio_issues,
    mission_portfolio_report,
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
        "nodes": [
            {
                "topic_id": "quests",
                "metadata": {
                    "mission_signature_contract": {
                        "required": True,
                        "signature_field": "mission_signature",
                    }
                },
            }
        ],
        "metadata": {
            "mission_signature_contract": {
                "domain_ids": ["quests"],
            }
        },
    }


def _signature(activity: str = "investigate") -> dict:
    return {
        "activity": activity,
        "target": "evidence_chain",
        "location": "restricted_site",
        "principal_actor": "local_sponsor",
        "antagonist": "institutional_rival",
        "pressure": "time_window",
        "resolution_modes": ["document", "negotiate"],
        "consequence_type": "access_shift",
    }


def _row(
    entity_id: str,
    slot_id: str,
    *,
    signature: dict | None = None,
    campaign_arc_id: str = "",
    arc_role: str = "",
    arc_sequence: int | None = None,
) -> dict:
    entity = {
        "id": entity_id,
        "manifest_slot_id": slot_id,
        "name": entity_id,
        "premise": f"A unique premise for {entity_id} with enough detail to avoid field duplication.",
    }
    if signature is not None:
        entity["mission_signature"] = signature
    if campaign_arc_id:
        entity["campaign_arc_id"] = campaign_arc_id
    if arc_role:
        entity["arc_role"] = arc_role
    if arc_sequence is not None:
        entity["arc_sequence"] = arc_sequence
    return {
        "topic_id": "quests",
        "candidate": {
            "topic_id": "quests",
            "entities": [entity],
            "documents": [],
            "facts": [],
            "relationships": [],
            "knowledge_rules": [],
            "story_threads": [],
            "provenance": {
                "generator": "deterministic_world_forge_v1",
                "entity_manifest_binding": {
                    "slot_ids": [slot_id],
                    "entity_ids": [entity_id],
                    "rewritten_provider_ids": {},
                },
            },
        },
    }


def test_profile_graph_injects_versioned_mission_contract() -> None:
    profile = resolve_or_generate_genre_profile(genre="cyberpunk").profile
    graph = build_profile_topic_graph(
        profile,
        campaign_template="cyberpunk",
        depth="quick",
    )
    node = graph.node_map()["opening_threads"]
    definitions = {
        str(row["field_id"]): dict(row)
        for row in node.metadata["field_definitions"]
    }

    assert node.metadata["schema_version"] == "rpg_profile_domain_opening_threads_v2"
    assert node.metadata["mission_signature_contract"]["required"] is True
    assert definitions["mission_signature"]["required"] is True
    assert definitions["mission_signature"]["value_type"] == "structured_object"
    assert definitions["campaign_arc_id"]["required"] is False
    assert definitions["arc_sequence"]["value_type"] == "integer"
    assert graph.metadata["mission_signature_contract"]["domain_ids"] == [
        "encounter_seeds",
        "opening_scenarios",
        "opening_threads",
        "quests",
    ]


def test_deterministic_mission_entities_receive_unique_signatures_without_fake_arcs() -> None:
    profile = resolve_or_generate_genre_profile(genre="cyberpunk").profile
    graph = build_profile_topic_graph(
        profile,
        campaign_template="cyberpunk",
        depth="standard",
    )
    node = graph.node_map()["opening_threads"]

    topic = generate_deterministic_profile_topic(
        node,
        campaign_context={"genre": "cyberpunk"},
        dependency_topics={},
    )

    signatures = [dict(entity["mission_signature"]) for entity in topic.entities]
    assert len(signatures) == node.target_count
    assert len({tuple(sorted(row.items(), key=lambda item: item[0])) for row in signatures}) == len(signatures)
    assert all(set(row) == {
        "activity",
        "target",
        "location",
        "principal_actor",
        "antagonist",
        "pressure",
        "resolution_modes",
        "consequence_type",
    } for row in signatures)
    assert all("campaign_arc_id" not in entity for entity in topic.entities)
    assert all("arc_role" not in entity for entity in topic.entities)
    assert all("arc_sequence" not in entity for entity in topic.entities)


def test_required_mission_signature_is_blocking_when_missing() -> None:
    issues = mission_portfolio_issues(
        [_row("ent:quest:one", "slot:quests:001")],
        _graph(),
    )

    assert any(issue.code == "mission_signature_required" for issue in issues)


def test_malformed_signature_reports_exact_component() -> None:
    malformed = _signature()
    malformed.pop("pressure")
    malformed["resolution_modes"] = []

    issues = mission_portfolio_issues(
        [_row("ent:quest:one", "slot:quests:001", signature=malformed)],
        _graph(),
    )
    codes = {issue.code for issue in issues}

    assert "mission_signature_component_required:pressure" in codes
    assert "mission_resolution_modes_required" in codes


def test_repeated_signature_without_arc_is_blocking() -> None:
    rows = [
        _row("ent:quest:one", "slot:quests:001", signature=_signature()),
        _row("ent:quest:two", "slot:quests:002", signature=_signature()),
    ]

    report = mission_portfolio_report(rows, _graph())

    assert report["passed"] is False
    repeated = next(
        issue for issue in report["issues"]
        if issue["code"] == "repeated_mission_signature"
    )
    assert repeated["fingerprint"].startswith("sha256:")
    assert [row["item_id"] for row in repeated["occurrences"]] == [
        "ent:quest:one",
        "ent:quest:two",
    ]


def test_repeated_signature_is_allowed_for_one_ordered_intentional_arc() -> None:
    rows = [
        _row(
            "ent:quest:one",
            "slot:quests:001",
            signature=_signature(),
            campaign_arc_id="arc:water-rights",
            arc_role="setup",
            arc_sequence=1,
        ),
        _row(
            "ent:quest:two",
            "slot:quests:002",
            signature=_signature(),
            campaign_arc_id="arc:water-rights",
            arc_role="reversal",
            arc_sequence=2,
        ),
    ]

    report = mission_portfolio_report(rows, _graph())

    assert report["passed"] is True
    assert report["issues"] == []
    assert report["checks"]["declared_arc_count"] == 1


@pytest.mark.parametrize(
    ("arc_id", "role", "sequence"),
    [
        ("arc:one", "", 1),
        ("arc:one", "setup", None),
        ("", "setup", 1),
        ("arc:one", "setup", 0),
    ],
)
def test_partial_arc_declaration_is_blocking(
    arc_id: str,
    role: str,
    sequence: int | None,
) -> None:
    issues = mission_portfolio_issues(
        [
            _row(
                "ent:quest:one",
                "slot:quests:001",
                signature=_signature(),
                campaign_arc_id=arc_id,
                arc_role=role,
                arc_sequence=sequence,
            )
        ],
        _graph(),
    )

    assert any(
        issue.code == "campaign_arc_declaration_incomplete" for issue in issues
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

    with pytest.raises(MissionPortfolioCompilationError):
        generation_compilation.compile_world_generation_certified_artifact(
            run={"run_id": "run:1", "graph": _graph()},
            world={"id": "world:1"},
            topic_rows=[_row("ent:quest:one", "slot:quests:001")],
            revision=1,
        )

    assert called is False


def test_diagnostic_compilation_retains_mission_report(
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
        topic_rows=[_row("ent:quest:one", "slot:quests:001")],
        revision=1,
    )

    report = artifact.certification["mission_portfolio"]
    assert report["passed"] is False
    assert artifact.certification["launch_ready"] is False
    assert "mission_portfolio" in artifact.certification["missing_requirements"]


def test_publication_transaction_surfaces_mission_report_failure() -> None:
    report = publication_transaction_report(
        {
            "run_id": "run:1",
            "world_id": "world:1",
            "status": "review",
            "progress": {"publication_blocked": False},
        },
        {
            "launch_ready": False,
            "missing_requirements": ["mission_portfolio"],
            "mission_portfolio": {
                "passed": False,
                "issues": [{"code": "mission_signature_required"}],
            },
        },
    )

    assert report["publishable"] is False
    assert "mission_portfolio" in report["failed_reports"]
