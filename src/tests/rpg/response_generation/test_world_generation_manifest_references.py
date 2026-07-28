from __future__ import annotations

import pytest

from app.rpg.worlds import generation_compilation
from app.rpg.worlds.generation_manifest_references import (
    ManifestReferenceCompilationError,
    manifest_reference_issues,
    manifest_reference_report,
)
from app.rpg.worlds.generation_publication import WorldGenerationPublication


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
        "metadata": {
            "resolved_profile": {
                "domains": [
                    {
                        "domain_id": "actors",
                        "entity_kind": "actor",
                        "fields": [
                            {
                                "field_id": "current_place",
                                "value_type": "entity_ref",
                                "allowed_target_domains": ["places"],
                            }
                        ],
                    },
                    {
                        "domain_id": "places",
                        "entity_kind": "place",
                        "fields": [],
                    },
                ]
            }
        }
    }


def _row(
    topic_id: str,
    entity_id: str,
    slot_id: str,
    *,
    entity: dict | None = None,
    extra: dict | None = None,
    aliases: dict[str, str] | None = None,
) -> dict:
    payload = {
        "topic_id": topic_id,
        "entities": [
            {
                "id": entity_id,
                "manifest_slot_id": slot_id,
                **dict(entity or {}),
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
                "rewritten_provider_ids": dict(aliases or {}),
            },
        },
    }
    payload.update(dict(extra or {}))
    return {"topic_id": topic_id, "candidate": payload}


def _valid_rows() -> list[dict]:
    places = _row(
        "places",
        "ent:place:harbor",
        "slot:places:001",
        entity={"name": "Harbor"},
    )
    actors = _row(
        "actors",
        "ent:actor:warden",
        "slot:actors:001",
        entity={
            "name": "Warden",
            "current_place": "ent:place:harbor",
            "nested": {"location_id": "ent:place:harbor"},
        },
        extra={
            "documents": [
                {
                    "document_id": "doc:warden",
                    "entities": ["ent:actor:warden", "ent:place:harbor"],
                    "canonical_source_fact_ids": ["fact:warden"],
                }
            ],
            "facts": [
                {
                    "id": "fact:warden",
                    "entity_refs": ["ent:actor:warden"],
                }
            ],
            "relationships": [
                {
                    "id": "rel:warden-harbor",
                    "source_id": "ent:actor:warden",
                    "target_id": "ent:place:harbor",
                }
            ],
            "story_threads": [
                {
                    "id": "thread:warden",
                    "actor_ids": ["ent:actor:warden"],
                    "location_ids": ["ent:place:harbor"],
                }
            ],
        },
    )
    return [places, actors]


def test_recursive_reference_closure_accepts_manifest_owned_world() -> None:
    report = manifest_reference_report(_valid_rows(), _graph())

    assert report["passed"] is True
    assert report["issues"] == []
    assert report["checks"]["entity_count"] == 2
    assert report["checks"]["profile_reference_field_count"] == 1


def test_profile_declared_reference_without_id_suffix_is_scanned() -> None:
    rows = _valid_rows()
    rows[1]["candidate"]["entities"][0]["current_place"] = "ent:place:missing"

    issues = manifest_reference_issues(rows, _graph())

    assert any(
        issue.code == "unresolved_canonical_entity_reference"
        and issue.path.endswith("/current_place")
        and issue.target_id == "ent:place:missing"
        for issue in issues
    )


def test_retained_provider_alias_is_distinguished_from_unknown_reference() -> None:
    rows = _valid_rows()
    rows[1]["candidate"]["provenance"]["entity_manifest_binding"][
        "rewritten_provider_ids"
    ] = {"provider:harbor": "ent:place:harbor"}
    rows[1]["candidate"]["relationships"][0]["target_id"] = "provider:harbor"

    issues = manifest_reference_issues(rows, _graph())

    assert any(
        issue.code == "legacy_entity_alias_retained"
        and issue.target_id == "provider:harbor"
        for issue in issues
    )


def test_reference_to_existing_unowned_entity_is_reported_precisely() -> None:
    rows = _valid_rows()
    rows[0]["candidate"]["entities"].append(
        {"id": "ent:place:unowned", "name": "Unowned"}
    )
    rows[1]["candidate"]["entities"][0]["nested"][
        "location_id"
    ] = "ent:place:unowned"

    issues = manifest_reference_issues(rows, _graph())
    codes = {issue.code for issue in issues}

    assert "entity_not_manifest_owned" in codes
    assert "reference_to_unowned_entity" in codes


def test_non_entity_identity_and_fact_fields_are_not_misclassified() -> None:
    rows = _valid_rows()
    document = rows[1]["candidate"]["documents"][0]
    document["topic_id"] = "actors"
    document["map_id"] = "map:harbor"
    document["source_fact_ids"] = ["fact:warden"]

    report = manifest_reference_report(rows, _graph())

    assert report["passed"] is True


def test_certified_compilation_fails_before_legacy_compiler_on_open_reference(
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
    rows = _valid_rows()
    rows[1]["candidate"]["relationships"][0]["target_id"] = "ent:place:missing"

    with pytest.raises(ManifestReferenceCompilationError) as exc_info:
        generation_compilation.compile_world_generation_certified_artifact(
            run={"run_id": "run:1", "graph": _graph()},
            world={"id": "world:1"},
            topic_rows=rows,
            revision=1,
        )

    assert called is False
    assert any(
        issue.code == "unresolved_canonical_entity_reference"
        for issue in exc_info.value.issues
    )


def test_diagnostic_compilation_retains_reference_closure_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        generation_compilation,
        "compile_world_generation_publication",
        lambda **_kwargs: _publication(),
    )
    rows = _valid_rows()
    rows[1]["candidate"]["relationships"][0]["target_id"] = "ent:place:missing"

    artifact = generation_compilation.compile_world_generation_diagnostic_draft(
        run={"run_id": "run:1", "graph": _graph()},
        world={"id": "world:1"},
        topic_rows=rows,
        revision=1,
    )

    report = artifact.certification["manifest_reference_closure"]
    assert artifact.certification["launch_ready"] is False
    assert "manifest_reference_closure" in artifact.certification[
        "missing_requirements"
    ]
    assert report["passed"] is False
