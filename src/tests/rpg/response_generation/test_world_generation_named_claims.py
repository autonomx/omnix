from __future__ import annotations

import pytest

from app.rpg.worlds import generation_compilation
from app.rpg.worlds.generation_named_claims import (
    ObjectiveNamedClaimCompilationError,
    objective_named_claim_issues,
    objective_named_claim_report,
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


def _row(topic_id: str, entity: dict, ordinal: int = 1) -> dict:
    entity_id = str(entity["id"])
    slot_id = f"slot:{topic_id}:{ordinal:03d}"
    return {
        "topic_id": topic_id,
        "candidate": {
            "topic_id": topic_id,
            "entities": [
                {
                    "manifest_slot_id": slot_id,
                    **entity,
                }
            ],
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


def test_registered_named_event_resolves_deterministically() -> None:
    rows = [
        _row(
            "history_timeline",
            {
                "id": "ent:event:data-wars",
                "name": "Data Sovereignty Wars",
            },
        ),
        _row(
            "groups",
            {
                "id": "ent:institution:archive",
                "name": "Civic Archive",
                "backstory": (
                    "The Civic Archive was created during the Data Sovereignty Wars "
                    "to preserve public ownership records."
                ),
            },
        ),
    ]

    report = objective_named_claim_report(rows)

    assert report["passed"] is True
    assert report["checks"] == {
        "claim_count": 1,
        "resolved_claim_count": 1,
        "unresolved_claim_count": 0,
        "ambiguous_claim_count": 0,
    }
    claim = report["claims"][0]
    assert claim["subject_id"] == "ent:institution:archive"
    assert claim["predicate"] == "historical_context"
    assert claim["mentioned_name"] == "Data Sovereignty Wars"
    assert claim["resolved_entity_ids"] == ["ent:event:data-wars"]


def test_registered_alias_resolves_without_creating_shadow_canon() -> None:
    rows = [
        _row(
            "groups",
            {
                "id": "ent:group:northern-watch",
                "name": "Northern Watch Command",
                "aliases": ["Northern Watch"],
            },
        ),
        _row(
            "actors",
            {
                "id": "ent:actor:aldric",
                "name": "Captain Aldric",
                "backstory": "Captain Aldric belongs to the Northern Watch.",
            },
        ),
    ]

    report = objective_named_claim_report(rows)

    assert report["passed"] is True
    assert report["claims"][0]["resolved_entity_ids"] == [
        "ent:group:northern-watch"
    ]


def test_unresolved_historical_name_is_blocking() -> None:
    rows = [
        _row(
            "groups",
            {
                "id": "ent:institution:archive",
                "name": "Civic Archive",
                "backstory": (
                    "The Civic Archive was created during the Data Sovereignty Wars "
                    "to preserve public ownership records."
                ),
            },
        )
    ]

    issues = objective_named_claim_issues(rows)

    assert len(issues) == 1
    issue = issues[0]
    assert issue.code == "unresolved_objective_named_claim"
    assert issue.claim.mentioned_name == "Data Sovereignty Wars"
    assert issue.claim.resolution == "unresolved"
    assert issue.claim.source_section == "backstory"


def test_ambiguous_alias_is_blocking() -> None:
    rows = [
        _row(
            "groups",
            {
                "id": "ent:group:north-one",
                "name": "Northern Watch First Command",
                "aliases": ["Northern Watch"],
            },
        ),
        _row(
            "groups",
            {
                "id": "ent:group:north-two",
                "name": "Northern Watch Second Command",
                "aliases": ["Northern Watch"],
            },
            ordinal=2,
        ),
        _row(
            "actors",
            {
                "id": "ent:actor:aldric",
                "name": "Captain Aldric",
                "backstory": "Captain Aldric belongs to the Northern Watch.",
            },
        ),
    ]

    issues = objective_named_claim_issues(rows)

    assert len(issues) == 1
    assert issues[0].code == "ambiguous_objective_named_claim"
    assert issues[0].claim.resolved_entity_ids == (
        "ent:group:north-one",
        "ent:group:north-two",
    )


def test_subjective_dossier_section_does_not_create_objective_claim() -> None:
    rows = [
        _row(
            "actors",
            {
                "id": "ent:actor:rumour-broker",
                "name": "Rumour Broker",
                "dossier": {
                    "sections": [
                        {
                            "id": "rumours",
                            "title": "Rumours",
                            "assertion_mode": "rumor",
                            "paragraphs": [
                                "Some patrons insist the broker was founded by the Ghost Council."
                            ],
                        }
                    ]
                },
            },
        )
    ]

    report = objective_named_claim_report(rows)

    assert report["passed"] is True
    assert report["claims"] == []


def test_objective_dossier_history_reports_unresolved_name_and_source() -> None:
    rows = [
        _row(
            "groups",
            {
                "id": "ent:group:archive",
                "name": "Archive Circle",
                "dossier": {
                    "sections": [
                        {
                            "id": "history",
                            "title": "History",
                            "assertion_mode": "objective",
                            "paragraphs": [
                                "The Circle was formed after the Glass Meridian Uprising."
                            ],
                        }
                    ]
                },
            },
        )
    ]

    issues = objective_named_claim_issues(rows)

    assert len(issues) == 1
    assert issues[0].claim.source_section == "history"
    assert issues[0].claim.assertion_mode == "objective"
    assert issues[0].claim.path.endswith("/paragraphs/0")
    assert issues[0].claim.mentioned_name == "Glass Meridian Uprising"


def test_lowercase_generic_history_phrase_is_ignored() -> None:
    rows = [
        _row(
            "groups",
            {
                "id": "ent:group:archive",
                "name": "Archive Circle",
                "backstory": "The Circle reorganised after the crisis and opened new records.",
            },
        )
    ]

    report = objective_named_claim_report(rows)

    assert report["passed"] is True
    assert report["claims"] == []


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
    rows = [
        _row(
            "groups",
            {
                "id": "ent:institution:archive",
                "name": "Civic Archive",
                "backstory": "The Archive was created during the Data Sovereignty Wars.",
            },
        )
    ]

    with pytest.raises(ObjectiveNamedClaimCompilationError):
        generation_compilation.compile_world_generation_certified_artifact(
            run={"run_id": "run:1", "graph": {}},
            world={"id": "world:1"},
            topic_rows=rows,
            revision=1,
        )

    assert called is False


def test_diagnostic_compilation_retains_named_claim_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        generation_compilation,
        "compile_world_generation_publication",
        lambda **_kwargs: _publication(),
    )
    rows = [
        _row(
            "groups",
            {
                "id": "ent:institution:archive",
                "name": "Civic Archive",
                "backstory": "The Archive was created during the Data Sovereignty Wars.",
            },
        )
    ]

    artifact = generation_compilation.compile_world_generation_diagnostic_draft(
        run={"run_id": "run:1", "graph": {}},
        world={"id": "world:1"},
        topic_rows=rows,
        revision=1,
    )

    report = artifact.certification["objective_named_claims"]
    assert report["passed"] is False
    assert report["issues"][0]["mentioned_name"] == "Data Sovereignty Wars"
    assert artifact.certification["launch_ready"] is False
    assert "objective_named_claims" in artifact.certification["missing_requirements"]


def test_publication_transaction_surfaces_named_claim_failure() -> None:
    report = publication_transaction_report(
        {
            "run_id": "run:1",
            "world_id": "world:1",
            "status": "review",
            "progress": {"publication_blocked": False},
        },
        {
            "launch_ready": False,
            "missing_requirements": ["objective_named_claims"],
            "objective_named_claims": {
                "passed": False,
                "issues": [{"code": "unresolved_objective_named_claim"}],
            },
        },
    )

    assert report["publishable"] is False
    assert "objective_named_claims" in report["failed_reports"]
