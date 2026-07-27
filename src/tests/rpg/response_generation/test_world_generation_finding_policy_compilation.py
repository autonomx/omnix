from __future__ import annotations

import pytest

from app.rpg.worlds import generation_compilation
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


def _review_result(*, severity: str, code: str) -> dict:
    return {
        "topic_id": "actors",
        "status": "accepted",
        "validation": {
            "waiver_status": "active",
            "outstanding_findings": [
                {
                    "code": code,
                    "severity": severity,
                    "item_id": "ent:actor:001",
                    "message": "Retained finding.",
                }
            ],
            "waiver": {
                "status": "active",
                "reason": "Reviewed by the Game Master.",
                "accepted_by": "local-game-master",
                "accepted_at": "2026-07-27T23:00:00+00:00",
            },
        },
    }


def test_warning_waiver_remains_visible_without_blocking_certification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        generation_compilation,
        "compile_world_generation_publication",
        lambda **_kwargs: _publication(),
    )

    artifact = generation_compilation.compile_world_generation_certified_artifact(
        run={"run_id": "run:1", "graph": {}},
        world={"id": "world:1"},
        topic_rows=[],
        review_results=[_review_result(severity="warning", code="style_repetition")],
        revision=1,
    )

    policy = artifact.certification["finding_waiver_policy"]
    assert artifact.certification["launch_ready"] is True
    assert policy["passed"] is True
    assert policy["active_waiver_count"] == 1
    assert policy["active_waivers"][0]["reason"] == "Reviewed by the Game Master."


def test_error_waiver_marks_certification_not_launch_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        generation_compilation,
        "compile_world_generation_publication",
        lambda **_kwargs: _publication(),
    )

    artifact = generation_compilation.compile_world_generation_certified_artifact(
        run={"run_id": "run:1", "graph": {}},
        world={"id": "world:1"},
        topic_rows=[],
        review_results=[
            _review_result(severity="error", code="semantic_contradiction")
        ],
        revision=1,
    )

    policy = artifact.certification["finding_waiver_policy"]
    assert artifact.certification["launch_ready"] is False
    assert "finding_waiver_policy" in artifact.certification["missing_requirements"]
    assert policy["passed"] is False
    assert policy["invalid_waivers"][0]["policy_reason"] == "severity_not_waivable"
