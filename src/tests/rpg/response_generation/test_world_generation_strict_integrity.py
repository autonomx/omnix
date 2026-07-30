from __future__ import annotations

import pytest

from app.rpg.worlds import generation_compilation
from app.rpg.worlds.generation_publication import WorldGenerationPublication
from app.rpg.worlds.generation_strict_integrity import (
    DuplicateCanonCompilationError,
    duplicate_canon_identifiers,
)


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


def _duplicate_rows() -> list[dict]:
    return [
        {
            "topic_id": "threats",
            "candidate": {
                "topic_id": "threats",
                "entities": [{"id": "ent:threats:004", "name": "First"}],
            },
        },
        {
            "topic_id": "encounter_seeds",
            "candidate": {
                "topic_id": "encounter_seeds",
                "entities": [{"id": "ent:threats:004", "name": "Second"}],
            },
        },
    ]


def test_duplicates_report_collection_id_and_all_source_topics() -> None:
    duplicates = duplicate_canon_identifiers(_duplicate_rows())

    assert len(duplicates) == 1
    duplicate = duplicates[0]
    assert duplicate.collection == "entities"
    assert duplicate.item_id == "ent:threats:004"
    assert duplicate.source_topic_ids == ("threats", "encounter_seeds")
    assert duplicate.occurrences == 2


def test_duplicate_inside_one_topic_is_not_silently_collapsed() -> None:
    duplicates = duplicate_canon_identifiers(
        [
            {
                "topic_id": "actors",
                "candidate": {
                    "entities": [
                        {"id": "ent:actor:001", "name": "One"},
                        {"id": "ent:actor:001", "name": "Two"},
                    ]
                },
            }
        ]
    )

    assert duplicates[0].source_topic_ids == ("actors",)
    assert duplicates[0].occurrences == 2


def test_certified_compilation_fails_before_legacy_compiler_can_choose_winner(
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

    with pytest.raises(DuplicateCanonCompilationError) as exc_info:
        generation_compilation.compile_world_generation_certified_artifact(
            run={"run_id": "run:1"},
            world={"id": "world:1"},
            topic_rows=_duplicate_rows(),
            revision=2,
        )

    assert called is False
    report = exc_info.value.as_dict()
    assert report["ok"] is False
    assert report["duplicates"][0]["item_id"] == "ent:threats:004"


def test_diagnostic_compilation_retains_duplicate_report_without_release_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        generation_compilation,
        "compile_world_generation_publication",
        lambda **_kwargs: _publication(),
    )

    artifact = generation_compilation.compile_world_generation_diagnostic_draft(
        run={"run_id": "run:1"},
        world={"id": "world:1"},
        topic_rows=_duplicate_rows(),
        revision=2,
    )
    payload = artifact.as_dict()

    assert payload["certification"]["launch_ready"] is False
    assert payload["certification"]["strict_integrity"]["passed"] is False
    assert payload["certification"]["missing_requirements"] == ["strict_integrity"]
    assert "world_release" not in payload
