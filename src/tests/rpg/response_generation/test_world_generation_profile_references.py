from __future__ import annotations

import pytest

from app.rpg.worlds import generation_compilation
from app.rpg.worlds.generation_profile_references import (
    ProfileReferenceCompilationError,
    profile_reference_issues,
    profile_reference_report,
)
from app.rpg.worlds.generation_publication import WorldGenerationPublication


class _Document:
    def __init__(self, kind: str) -> None:
        self.kind = kind

    def model_dump(self, *, mode: str) -> dict:
        assert mode == "json"
        return {"kind": self.kind}


class _Release(_Document):
    artifact_stage = "playtested"
    runtime_seed = {"seed": "runtime"}
    materialization = {"hub_location_id": "ent:place:001"}
    playtest_report = {"passed": True}


def _publication() -> WorldGenerationPublication:
    return WorldGenerationPublication(
        world_revision=_Document("revision"),  # type: ignore[arg-type]
        world_release=_Release("release"),  # type: ignore[arg-type]
        certification={"launch_ready": True, "missing_requirements": []},
    )


def _graph() -> dict:
    return {
        "metadata": {
            "resolved_profile": {
                "domains": [
                    {
                        "domain_id": "groups",
                        "entity_kind": "group",
                        "fields": [
                            {"field_id": "name", "value_type": "string"}
                        ],
                    },
                    {
                        "domain_id": "actors",
                        "entity_kind": "actor",
                        "fields": [
                            {
                                "field_id": "group_ids",
                                "value_type": "entity_ref_list",
                                "allowed_target_domains": ["groups"],
                            },
                            {
                                "field_id": "mentor_id",
                                "value_type": "entity_ref",
                                "allowed_target_domains": ["actors"],
                            },
                        ],
                    },
                ]
            }
        }
    }


def _rows(*, group_ids: list[str], mentor_id: str = "") -> list[dict]:
    return [
        {
            "topic_id": "groups",
            "candidate": {
                "topic_id": "groups",
                "entities": [{"id": "ent:group:001", "name": "The Guild"}],
            },
        },
        {
            "topic_id": "actors",
            "candidate": {
                "topic_id": "actors",
                "entities": [
                    {
                        "id": "ent:actor:001",
                        "name": "Ari",
                        "group_ids": group_ids,
                        "mentor_id": mentor_id,
                    },
                    {
                        "id": "ent:actor:002",
                        "name": "Bo",
                        "group_ids": [],
                    },
                ],
            },
        },
    ]


def test_all_profile_declared_references_are_validated() -> None:
    report = profile_reference_report(
        _rows(group_ids=["ent:group:001"], mentor_id="ent:actor:002"),
        _graph(),
    )

    assert report["passed"] is True
    assert report["issues"] == []
    assert report["checks"]["profile_domains"] == 2


def test_unresolved_profile_reference_reports_precise_source() -> None:
    issues = profile_reference_issues(
        _rows(group_ids=["ent:group:missing"]),
        _graph(),
    )

    assert len(issues) == 1
    issue = issues[0]
    assert issue.code == "unresolved_profile_reference"
    assert issue.source_domain == "actors"
    assert issue.entity_id == "ent:actor:001"
    assert issue.field_id == "group_ids"
    assert issue.target_id == "ent:group:missing"
    assert issue.allowed_target_domains == ("groups",)


def test_reference_to_existing_entity_in_wrong_domain_is_rejected() -> None:
    issues = profile_reference_issues(
        _rows(group_ids=["ent:actor:002"]),
        _graph(),
    )

    assert len(issues) == 1
    issue = issues[0]
    assert issue.code == "profile_reference_wrong_domain"
    assert issue.target_id == "ent:actor:002"
    assert issue.actual_target_domain == "actors"
    assert issue.allowed_target_domains == ("groups",)


def test_certified_compilation_fails_before_legacy_compiler_on_bad_reference(
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

    with pytest.raises(ProfileReferenceCompilationError) as exc_info:
        generation_compilation.compile_world_generation_certified_artifact(
            run={"run_id": "run:1", "graph": _graph()},
            world={"id": "world:1"},
            topic_rows=_rows(group_ids=["ent:group:missing"]),
            revision=2,
        )

    assert called is False
    report = exc_info.value.as_dict()
    assert report["ok"] is False
    assert report["issues"][0]["field_id"] == "group_ids"


def test_diagnostic_compilation_retains_reference_report_without_release_claim(
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
        topic_rows=_rows(group_ids=["ent:group:missing"]),
        revision=2,
    )
    payload = artifact.as_dict()

    assert payload["certification"]["launch_ready"] is False
    assert payload["certification"]["profile_reference_integrity"]["passed"] is False
    assert payload["certification"]["missing_requirements"] == [
        "profile_reference_integrity"
    ]
    assert "world_release" not in payload
