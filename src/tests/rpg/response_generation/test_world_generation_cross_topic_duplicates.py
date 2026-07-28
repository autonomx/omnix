from __future__ import annotations

import pytest

from app.rpg.worlds import generation_compilation
from app.rpg.worlds.generation_cross_topic_duplicates import (
    CrossTopicDuplicateFieldCompilationError,
    cross_topic_duplicate_field_issues,
    cross_topic_duplicate_field_report,
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


def _row(
    topic_id: str,
    entity_id: str,
    slot_id: str,
    **fields: object,
) -> dict:
    return {
        "topic_id": topic_id,
        "candidate": {
            "topic_id": topic_id,
            "entities": [
                {
                    "id": entity_id,
                    "manifest_slot_id": slot_id,
                    "name": entity_id,
                    **fields,
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


def _duplicate_text() -> str:
    return (
        "The council diverts the eastern water allotment through a private gate, "
        "forcing neighbourhood delegates to bargain for every emergency delivery."
    )


def test_normalised_semantic_text_reused_across_topics_is_blocking() -> None:
    rows = [
        _row(
            "actors",
            "ent:actor:warden",
            "slot:actors:001",
            current_pressure=_duplicate_text(),
        ),
        _row(
            "institutions",
            "ent:institution:council",
            "slot:institutions:001",
            current_pressure="  " + _duplicate_text().upper() + "  ",
        ),
    ]

    report = cross_topic_duplicate_field_report(rows, {})

    assert report["passed"] is False
    assert report["checks"]["duplicate_signature_count"] == 1
    issue = report["issues"][0]
    assert issue["code"] == "cross_topic_duplicate_field"
    assert issue["field_id"] == "current_pressure"
    assert issue["severity"] == "error"
    assert [row["topic_id"] for row in issue["occurrences"]] == [
        "actors",
        "institutions",
    ]
    assert all(row["path"].endswith("/current_pressure") for row in issue["occurrences"])


def test_structured_objects_ignore_identifier_noise_when_content_is_copied() -> None:
    copied_detail = (
        "A damaged relay broadcasts the same evacuation order every night, "
        "drawing scavengers toward an exposed maintenance corridor."
    )
    rows = [
        _row(
            "places",
            "ent:place:relay",
            "slot:places:001",
            current_hazard={"source_id": "fact:one", "detail": copied_detail},
        ),
        _row(
            "threats",
            "ent:threat:signal",
            "slot:threats:001",
            current_hazard={"source_id": "fact:two", "detail": copied_detail},
        ),
    ]

    issues = cross_topic_duplicate_field_issues(rows, {})

    assert len(issues) == 1
    assert issues[0].field_id == "current_hazard"
    assert issues[0].sample.startswith("{")


def test_short_values_references_and_same_topic_reuse_are_ignored() -> None:
    rows = [
        _row(
            "actors",
            "ent:actor:one",
            "slot:actors:001",
            status="active",
            faction_id="ent:faction:shared",
            motto="Hold the line",
            goal=_duplicate_text(),
        ),
        _row(
            "actors",
            "ent:actor:two",
            "slot:actors:002",
            status="active",
            faction_id="ent:faction:shared",
            motto="Hold the line",
            goal=_duplicate_text(),
        ),
    ]

    report = cross_topic_duplicate_field_report(rows, {})

    assert report["passed"] is True
    assert report["issues"] == []


def test_profile_scoping_uses_declared_semantic_fields_only() -> None:
    graph = {
        "metadata": {
            "resolved_profile": {
                "domains": [
                    {
                        "domain_id": "actors",
                        "fields": [
                            {"field_id": "goal", "value_type": "string"},
                            {
                                "field_id": "faction_id",
                                "value_type": "entity_ref",
                            },
                        ],
                    },
                    {
                        "domain_id": "institutions",
                        "fields": [
                            {"field_id": "goal", "value_type": "string"},
                            {
                                "field_id": "faction_id",
                                "value_type": "entity_ref",
                            },
                        ],
                    },
                ]
            }
        }
    }
    rows = [
        _row(
            "actors",
            "ent:actor:one",
            "slot:actors:001",
            goal="A distinct actor objective with enough concrete detail to be substantial and unique.",
            hidden_copy=_duplicate_text(),
            faction_id="ent:faction:shared",
        ),
        _row(
            "institutions",
            "ent:institution:one",
            "slot:institutions:001",
            goal="A distinct institutional objective with enough concrete detail to remain unique.",
            hidden_copy=_duplicate_text(),
            faction_id="ent:faction:shared",
        ),
    ]

    report = cross_topic_duplicate_field_report(rows, graph)

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
    rows = [
        _row(
            "actors",
            "ent:actor:one",
            "slot:actors:001",
            goal=_duplicate_text(),
        ),
        _row(
            "institutions",
            "ent:institution:one",
            "slot:institutions:001",
            goal=_duplicate_text(),
        ),
    ]

    with pytest.raises(CrossTopicDuplicateFieldCompilationError):
        generation_compilation.compile_world_generation_certified_artifact(
            run={"run_id": "run:1", "graph": {}},
            world={"id": "world:1"},
            topic_rows=rows,
            revision=1,
        )

    assert called is False


def test_diagnostic_compilation_retains_duplicate_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        generation_compilation,
        "compile_world_generation_publication",
        lambda **_kwargs: _publication(),
    )
    rows = [
        _row(
            "actors",
            "ent:actor:one",
            "slot:actors:001",
            goal=_duplicate_text(),
        ),
        _row(
            "institutions",
            "ent:institution:one",
            "slot:institutions:001",
            goal=_duplicate_text(),
        ),
    ]

    artifact = generation_compilation.compile_world_generation_diagnostic_draft(
        run={"run_id": "run:1", "graph": {}},
        world={"id": "world:1"},
        topic_rows=rows,
        revision=1,
    )

    report = artifact.certification["cross_topic_duplicate_fields"]
    assert report["passed"] is False
    assert artifact.certification["launch_ready"] is False
    assert "cross_topic_duplicate_fields" in artifact.certification[
        "missing_requirements"
    ]


def test_publication_transaction_surfaces_duplicate_report_failure() -> None:
    report = publication_transaction_report(
        {
            "run_id": "run:1",
            "world_id": "world:1",
            "status": "review",
            "progress": {"publication_blocked": False},
        },
        {
            "launch_ready": False,
            "missing_requirements": ["cross_topic_duplicate_fields"],
            "cross_topic_duplicate_fields": {
                "passed": False,
                "issues": [{"code": "cross_topic_duplicate_field"}],
            },
        },
    )

    assert report["publishable"] is False
    assert "certification_report_failed" in report["reasons"]
    assert "cross_topic_duplicate_fields" in report["failed_reports"]
