from __future__ import annotations

import pytest

from app.rpg.worlds import generation_compilation
from app.rpg.worlds.generation_entity_contamination import (
    EntityIdentityContaminationCompilationError,
    entity_identity_contamination_issues,
    entity_identity_contamination_report,
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


def _actors(*entities: dict) -> list[dict]:
    return [_row("actors", entity, ordinal=index) for index, entity in enumerate(entities, start=1)]


def test_foreign_entity_as_self_subject_is_blocking() -> None:
    rows = _actors(
        {
            "id": "ent:actor:bran",
            "name": "Bran",
            "goal": "Elara seeks to control the eastern market before the next assembly.",
        },
        {
            "id": "ent:actor:elara",
            "name": "Elara",
            "goal": "Elara seeks to secure two independent supply routes.",
        },
    )

    report = entity_identity_contamination_report(rows, {})

    assert report["passed"] is False
    assert report["checks"]["foreign_identity_leak_count"] == 1
    issue = report["issues"][0]
    assert issue["code"] == "foreign_entity_identity_leak"
    assert issue["entity_id"] == "ent:actor:bran"
    assert issue["foreign_entity_id"] == "ent:actor:elara"
    assert issue["foreign_name"] == "Elara"
    assert issue["field_id"] == "goal"


def test_foreign_possessive_owner_is_blocking() -> None:
    rows = _actors(
        {
            "id": "ent:actor:bran",
            "name": "Bran",
            "current_pressure": (
                "Elara's current pressure is a collapsing supply agreement with the docks."
            ),
        },
        {"id": "ent:actor:elara", "name": "Elara", "goal": "Elara seeks stability."},
    )

    issues = entity_identity_contamination_issues(rows, {})

    assert len(issues) == 1
    assert issues[0].code == "foreign_entity_identity_leak"
    assert issues[0].field_id == "current_pressure"


def test_external_actor_is_allowed_when_current_entity_is_named() -> None:
    rows = _actors(
        {
            "id": "ent:actor:bran",
            "name": "Bran",
            "current_pressure": (
                "Elara controls the only spare shipment, leaving Bran without enough stock "
                "for the coming market day."
            ),
        },
        {"id": "ent:actor:elara", "name": "Elara", "goal": "Elara seeks stability."},
    )

    report = entity_identity_contamination_report(rows, {})

    assert report["passed"] is True
    assert report["issues"] == []


def test_relationship_field_is_excluded_from_self_identity_checks() -> None:
    rows = _actors(
        {
            "id": "ent:actor:bran",
            "name": "Bran",
            "relationships": "Elara seeks Bran's help but refuses his first offer.",
        },
        {"id": "ent:actor:elara", "name": "Elara", "goal": "Elara seeks stability."},
    )

    report = entity_identity_contamination_report(rows, {})

    assert report["passed"] is True


def test_nested_structured_self_field_is_scanned() -> None:
    rows = _actors(
        {
            "id": "ent:actor:bran",
            "name": "Bran",
            "reaction_conditions": {
                "trigger": "Elara intends to close the western gate before dawn."
            },
        },
        {"id": "ent:actor:elara", "name": "Elara", "goal": "Elara seeks stability."},
    )

    issues = entity_identity_contamination_issues(rows, {})

    assert len(issues) == 1
    assert issues[0].path.endswith("/reaction_conditions/trigger")


def test_objective_dossier_overview_is_scanned() -> None:
    rows = _actors(
        {
            "id": "ent:actor:bran",
            "name": "Bran",
            "dossier": {
                "sections": [
                    {
                        "id": "overview",
                        "title": "Overview",
                        "paragraphs": [
                            "Elara is a guarded merchant who keeps three competing ledgers."
                        ],
                    }
                ]
            },
        },
        {"id": "ent:actor:elara", "name": "Elara", "goal": "Elara seeks stability."},
    )

    issues = entity_identity_contamination_issues(rows, {})

    assert len(issues) == 1
    assert issues[0].field_id == "overview"
    assert "/dossier/sections/0/paragraphs/0" in issues[0].path


def test_dossier_relationship_section_is_excluded() -> None:
    rows = _actors(
        {
            "id": "ent:actor:bran",
            "name": "Bran",
            "dossier": {
                "sections": [
                    {
                        "id": "relationships",
                        "title": "Relationships",
                        "paragraphs": [
                            "Elara seeks Bran's cooperation but distrusts his suppliers."
                        ],
                    }
                ]
            },
        },
        {"id": "ent:actor:elara", "name": "Elara", "goal": "Elara seeks stability."},
    )

    report = entity_identity_contamination_report(rows, {})

    assert report["passed"] is True


def test_explicit_pronoun_disagreement_is_blocking() -> None:
    rows = _actors(
        {
            "id": "ent:actor:kaelen",
            "name": "Kaelen Voss",
            "pronouns": "he/him",
            "goal": "She seeks access to the sealed relay before the patrol changes.",
        }
    )

    issues = entity_identity_contamination_issues(rows, {})

    assert len(issues) == 1
    issue = issues[0]
    assert issue.code == "pronoun_identity_mismatch"
    assert issue.expected_pronouns == ("he", "him", "his")
    assert issue.observed_pronoun == "she"


def test_matching_explicit_pronoun_is_allowed() -> None:
    rows = _actors(
        {
            "id": "ent:actor:kaelen",
            "name": "Kaelen Voss",
            "pronouns": "he/him",
            "goal": "He seeks access to the sealed relay before the patrol changes.",
        }
    )

    report = entity_identity_contamination_report(rows, {})

    assert report["passed"] is True


def test_pronoun_sentence_naming_another_entity_is_not_assumed_to_be_self() -> None:
    rows = _actors(
        {
            "id": "ent:actor:kaelen",
            "name": "Kaelen Voss",
            "pronouns": "he/him",
            "goal": "She warns Elara that the sealed relay will fail before dawn.",
        },
        {"id": "ent:actor:elara", "name": "Elara", "goal": "Elara seeks stability."},
    )

    report = entity_identity_contamination_report(rows, {})

    assert report["passed"] is True


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
    rows = _actors(
        {
            "id": "ent:actor:bran",
            "name": "Bran",
            "goal": "Elara seeks to control the eastern market before the next assembly.",
        },
        {"id": "ent:actor:elara", "name": "Elara", "goal": "Elara seeks stability."},
    )

    with pytest.raises(EntityIdentityContaminationCompilationError):
        generation_compilation.compile_world_generation_certified_artifact(
            run={"run_id": "run:1", "graph": {}},
            world={"id": "world:1"},
            topic_rows=rows,
            revision=1,
        )

    assert called is False


def test_diagnostic_compilation_retains_contamination_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        generation_compilation,
        "compile_world_generation_publication",
        lambda **_kwargs: _publication(),
    )
    rows = _actors(
        {
            "id": "ent:actor:bran",
            "name": "Bran",
            "goal": "Elara seeks to control the eastern market before the next assembly.",
        },
        {"id": "ent:actor:elara", "name": "Elara", "goal": "Elara seeks stability."},
    )

    artifact = generation_compilation.compile_world_generation_diagnostic_draft(
        run={"run_id": "run:1", "graph": {}},
        world={"id": "world:1"},
        topic_rows=rows,
        revision=1,
    )

    report = artifact.certification["entity_identity_contamination"]
    assert report["passed"] is False
    assert artifact.certification["launch_ready"] is False
    assert "entity_identity_contamination" in artifact.certification[
        "missing_requirements"
    ]


def test_publication_transaction_surfaces_contamination_failure() -> None:
    report = publication_transaction_report(
        {
            "run_id": "run:1",
            "world_id": "world:1",
            "status": "review",
            "progress": {"publication_blocked": False},
        },
        {
            "launch_ready": False,
            "missing_requirements": ["entity_identity_contamination"],
            "entity_identity_contamination": {
                "passed": False,
                "issues": [{"code": "foreign_entity_identity_leak"}],
            },
        },
    )

    assert report["publishable"] is False
    assert "entity_identity_contamination" in report["failed_reports"]
