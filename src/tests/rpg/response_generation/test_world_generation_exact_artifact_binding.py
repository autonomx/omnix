from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.rpg.worlds import generation_exact_artifact
from app.rpg.worlds.generation_exact_artifact import (
    ExactArtifactBindingError,
    exact_artifact_binding_report,
    prepare_world_generation_audit_rows,
    require_exact_artifact_binding,
)


def _graph() -> dict:
    return {
        "graph_version": "exact-artifact-test-v1",
        "campaign_template": "classic_fantasy",
        "depth": "quick",
        "nodes": [
            {
                "topic_id": "places",
                "title": "Places",
                "category": "lore",
                "dependencies": [],
                "generator_role": "geography_architect",
                "required_before_launch": True,
                "visibility": "game_master_canon",
                "target_count": 1,
                "metadata": {},
            }
        ],
        "metadata": {},
    }


def _rows() -> list[dict]:
    return [
        {
            "topic_id": "places",
            "status": "ready",
            "content": {
                "topic_id": "places",
                "documents": [],
                "entities": [{"id": "ent:place:1", "title": "Old Name"}],
                "facts": [],
                "relationships": [],
                "knowledge_rules": [],
                "story_threads": [],
                "provenance": {},
            },
        }
    ]


def test_prepared_rows_are_the_normalised_publication_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def normalise(generation: object, **_kwargs: object) -> object:
        topic = generation.topics[0]  # type: ignore[attr-defined]
        updated = replace(
            topic,
            entities=({"id": "ent:place:1", "name": "Normalised Name"},),
        )
        return replace(generation, topics=(updated,))

    monkeypatch.setattr(
        generation_exact_artifact,
        "repair_generation_contracts",
        normalise,
    )

    prepared = prepare_world_generation_audit_rows(
        run={"graph": _graph(), "context": {}},
        world={"id": "world:1"},
        topic_rows=_rows(),
    )

    assert prepared.topic_rows[0]["status"] == "ready"
    content = prepared.topic_rows[0]["content"]
    assert content["entities"][0]["name"] == "Normalised Name"
    assert prepared.topic_rows[0]["content_hash"].startswith("sha256:")
    assert prepared.content_hash.startswith("sha256:")


def test_published_revision_must_expose_the_exact_audited_topic_hashes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        generation_exact_artifact,
        "repair_generation_contracts",
        lambda generation, **_kwargs: generation,
    )
    prepared = prepare_world_generation_audit_rows(
        run={"graph": _graph(), "context": {}},
        world={"id": "world:1"},
        topic_rows=_rows(),
    )
    publication = SimpleNamespace(
        world_revision=SimpleNamespace(
            provenance={"topic_hashes": dict(prepared.topic_hashes)},
            content_hash="sha256:" + "a" * 64,
        )
    )

    report = exact_artifact_binding_report(prepared, publication)

    assert report["passed"] is True
    require_exact_artifact_binding(report)

    publication.world_revision.provenance["topic_hashes"]["places"] = (
        "sha256:" + "b" * 64
    )
    failed = exact_artifact_binding_report(prepared, publication)

    assert failed["passed"] is False
    assert failed["issues"][0]["code"] == "published_topic_hashes_mismatch"
    with pytest.raises(ExactArtifactBindingError):
        require_exact_artifact_binding(failed)
