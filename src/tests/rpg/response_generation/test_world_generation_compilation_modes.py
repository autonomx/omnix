from __future__ import annotations

import pytest

from app.rpg.worlds import generation_compilation
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
        certification={"launch_ready": True},
    )


def _compile_kwargs() -> dict:
    return {
        "run": {"run_id": "run:1"},
        "world": {"id": "world:1"},
        "topic_rows": [],
        "revision": 2,
    }


def test_diagnostic_mode_exposes_no_release_document(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        generation_compilation,
        "compile_world_generation_publication",
        lambda **_kwargs: _publication(),
    )

    artifact = generation_compilation.compile_world_generation_diagnostic_draft(
        **_compile_kwargs()
    )
    payload = artifact.as_dict()

    assert payload["mode"] == "diagnostic_draft"
    assert payload["world_revision"] == {"kind": "revision"}
    assert payload["certification"]["compilation_mode"] == "diagnostic_draft"
    assert payload["runtime_seed"] == {"seed": "runtime"}
    assert "world_release" not in payload
    assert "release" not in payload
    assert "release_hash" not in payload


def test_certified_mode_is_the_only_release_shaped_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        generation_compilation,
        "compile_world_generation_publication",
        lambda **_kwargs: _publication(),
    )

    artifact = generation_compilation.compile_world_generation_certified_artifact(
        **_compile_kwargs()
    )
    payload = artifact.as_dict()

    assert payload["mode"] == "certified_release"
    assert payload["world_revision"] == {"kind": "revision"}
    assert payload["world_release"] == {"kind": "release"}
    assert payload["certification"]["compilation_mode"] == "certified_release"


def test_unknown_compilation_mode_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        generation_compilation,
        "compile_world_generation_publication",
        lambda **_kwargs: _publication(),
    )

    with pytest.raises(
        ValueError,
        match="unsupported_world_generation_compilation_mode:preview_release",
    ):
        generation_compilation.compile_world_generation_artifact(
            mode="preview_release",  # type: ignore[arg-type]
            **_compile_kwargs(),
        )
