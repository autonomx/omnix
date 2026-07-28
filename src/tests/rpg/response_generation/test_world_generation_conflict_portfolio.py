from __future__ import annotations

import pytest

from app.rpg.worlds import generation_compilation
from app.rpg.worlds.generation_conflict_portfolio import (
    ConflictPortfolioCompilationError,
    conflict_portfolio_issues,
    conflict_portfolio_report,
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


def _conflict_rows(anchor_count: int) -> list[dict]:
    topics = (
        "pressures",
        "quests",
        "opening_threads",
        "encounter_seeds",
        "pressures",
        "quests",
        "opening_threads",
        "encounter_seeds",
    )
    counters: dict[str, int] = {}
    rows = []
    for index, topic_id in enumerate(topics, start=1):
        counters[topic_id] = counters.get(topic_id, 0) + 1
        entity = {
            "id": f"ent:conflict:{index}",
            "name": f"Conflict Vector {index}",
        }
        if index <= anchor_count:
            entity["group_ids"] = ["ent:group:omnicorp"]
        else:
            entity["group_ids"] = [f"ent:group:other-{index}"]
        rows.append(_row(topic_id, entity, counters[topic_id]))
    return rows


def test_canonical_anchor_over_half_the_conflict_portfolio_is_blocking() -> None:
    report = conflict_portfolio_report(_conflict_rows(5), {})

    assert report["passed"] is False
    issue = report["issues"][0]
    assert issue["code"] == "dominant_undeclared_conflict_anchor"
    assert issue["anchor"] == "ent:group:omnicorp"
    assert issue["count"] == 5
    assert issue["entity_ratio"] == 0.625
    assert issue["topic_count"] == 4
    assert all("group_ids" in row["source_fields"] for row in issue["occurrences"])


def test_exactly_half_the_conflict_portfolio_is_valid() -> None:
    report = conflict_portfolio_report(_conflict_rows(4), {})

    assert report["passed"] is True


def test_location_references_do_not_count_as_conflict_anchors() -> None:
    rows = []
    for index, topic_id in enumerate(
        ("pressures", "quests", "opening_threads", "encounter_seeds") * 2,
        start=1,
    ):
        rows.append(
            _row(
                topic_id,
                {
                    "id": f"ent:item:{index}",
                    "name": f"Item {index}",
                    "place_ids": ["ent:place:central"],
                },
                ordinal=(index + 3) // 4,
            )
        )

    report = conflict_portfolio_report(rows, {})

    assert report["passed"] is True
    assert report["checks"]["tracked_anchor_count"] == 0


def test_exact_core_conflict_scope_exempts_dominant_anchor() -> None:
    rows = _conflict_rows(5)
    graph = {
        "metadata": {
            "core_conflicts": [
                {
                    "conflict_id": "core:omnicorp-control",
                    "anchors": ["ent:group:omnicorp"],
                    "entity_ids": [f"ent:conflict:{index}" for index in range(1, 6)],
                }
            ]
        }
    }

    report = conflict_portfolio_report(rows, graph)

    assert report["passed"] is True
    assert report["declared_core_conflicts"][0]["conflict_id"] == (
        "core:omnicorp-control"
    )


def test_incomplete_core_conflict_scope_does_not_exempt_extra_occurrence() -> None:
    rows = _conflict_rows(5)
    graph = {
        "metadata": {
            "core_conflicts": [
                {
                    "conflict_id": "core:omnicorp-control",
                    "anchors": ["ent:group:omnicorp"],
                    "entity_ids": [f"ent:conflict:{index}" for index in range(1, 5)],
                }
            ]
        }
    }

    issues = conflict_portfolio_issues(rows, graph)

    assert any(issue.anchor == "ent:group:omnicorp" for issue in issues)


def test_mission_antagonist_category_can_be_a_dominant_anchor() -> None:
    rows = []
    topics = (
        "quests",
        "encounter_seeds",
        "opening_threads",
        "opening_scenarios",
    ) * 2
    for index, topic_id in enumerate(topics, start=1):
        antagonist = "institutional_rival" if index <= 5 else f"rival_{index}"
        rows.append(
            _row(
                topic_id,
                {
                    "id": f"ent:mission:{index}",
                    "name": f"Mission {index}",
                    "mission_signature": {
                        "activity": f"activity_{index}",
                        "target": f"target_{index}",
                        "location": f"location_{index}",
                        "principal_actor": f"actor_{index}",
                        "antagonist": antagonist,
                        "pressure": f"pressure_{index}",
                        "resolution_modes": [f"resolution_{index}"],
                        "consequence_type": f"consequence_{index}",
                    },
                },
                ordinal=(index + 3) // 4,
            )
        )

    issues = conflict_portfolio_issues(rows, {})

    assert any(
        issue.anchor == "signature:antagonist:institutional_rival"
        for issue in issues
    )


def test_small_portfolio_does_not_trigger_below_minimum_count() -> None:
    rows = [
        _row(
            topic_id,
            {
                "id": f"ent:small:{index}",
                "name": f"Small Conflict {index}",
                "group_ids": ["ent:group:shared" if index <= 3 else "ent:group:other"],
            },
        )
        for index, topic_id in enumerate(
            ("pressures", "quests", "opening_threads", "encounter_seeds"),
            start=1,
        )
    ]

    report = conflict_portfolio_report(rows, {})

    assert report["passed"] is True


def _certification_rows() -> list[dict]:
    return [
        _row(
            "groups",
            {
                "id": "ent:group:omnicorp",
                "name": "Omni Corporation",
            },
        ),
        *[
            _row(
                topic_id,
                {
                    "id": f"ent:cert-conflict:{index}",
                    "name": f"Certified Conflict {index}",
                    "group_ids": [
                        "ent:group:omnicorp"
                        if index <= 5
                        else f"ent:cert-conflict:{index - 1}"
                    ],
                },
                ordinal=(index + 3) // 4,
            )
            for index, topic_id in enumerate(
                (
                    "pressures",
                    "quests",
                    "opening_threads",
                    "encounter_seeds",
                )
                * 2,
                start=1,
            )
        ],
    ]


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

    with pytest.raises(ConflictPortfolioCompilationError):
        generation_compilation.compile_world_generation_certified_artifact(
            run={"run_id": "run:1", "graph": {}},
            world={"id": "world:1"},
            topic_rows=_certification_rows(),
            revision=1,
        )

    assert called is False


def test_diagnostic_compilation_retains_conflict_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        generation_compilation,
        "compile_world_generation_publication",
        lambda **_kwargs: _publication(),
    )

    artifact = generation_compilation.compile_world_generation_diagnostic_draft(
        run={"run_id": "run:1", "graph": {}},
        world={"id": "world:1"},
        topic_rows=_certification_rows(),
        revision=1,
    )

    report = artifact.certification["conflict_portfolio"]
    assert report["passed"] is False
    assert artifact.certification["launch_ready"] is False
    assert "conflict_portfolio" in artifact.certification["missing_requirements"]


def test_publication_transaction_surfaces_conflict_failure() -> None:
    report = publication_transaction_report(
        {
            "run_id": "run:1",
            "world_id": "world:1",
            "status": "review",
            "progress": {"publication_blocked": False},
        },
        {
            "launch_ready": False,
            "missing_requirements": ["conflict_portfolio"],
            "conflict_portfolio": {
                "passed": False,
                "issues": [{"code": "dominant_undeclared_conflict_anchor"}],
            },
        },
    )

    assert report["publishable"] is False
    assert "conflict_portfolio" in report["failed_reports"]
