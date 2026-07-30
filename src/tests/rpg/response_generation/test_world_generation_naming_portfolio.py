from __future__ import annotations

import pytest

from app.rpg.worlds import generation_compilation
from app.rpg.worlds.generation_naming_portfolio import (
    NamingPortfolioCompilationError,
    naming_portfolio_issues,
    naming_portfolio_report,
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


def _row(topic_id: str, entity_id: str, name: str, ordinal: int = 1) -> dict:
    slot_id = f"slot:{topic_id}:{ordinal:03d}"
    return {
        "topic_id": topic_id,
        "candidate": {
            "topic_id": topic_id,
            "entities": [
                {
                    "id": entity_id,
                    "manifest_slot_id": slot_id,
                    "name": name,
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


def _portfolio(names: list[tuple[str, str]]) -> list[dict]:
    topic_cycle = ("actors", "places", "groups", "technology_augmentations")
    counters: dict[str, int] = {}
    rows = []
    for index, (entity_id, name) in enumerate(names):
        topic_id = topic_cycle[index % len(topic_cycle)]
        counters[topic_id] = counters.get(topic_id, 0) + 1
        rows.append(_row(topic_id, entity_id, name, counters[topic_id]))
    return rows


def _dominant_names() -> list[tuple[str, str]]:
    return [
        ("ent:1", "Neon Covenant"),
        ("ent:2", "Neon Meridian"),
        ("ent:3", "Neon Archive"),
        ("ent:4", "Neon Bastion"),
        ("ent:5", "Neon Trestle"),
        ("ent:6", "Amber Reach"),
        ("ent:7", "Copper Vale"),
        ("ent:8", "Glass Orchard"),
    ]


def test_undeclared_term_over_half_the_world_is_blocking() -> None:
    report = naming_portfolio_report(_portfolio(_dominant_names()), {})

    assert report["passed"] is False
    issue = next(
        item for item in report["issues"]
        if item["code"] == "dominant_undeclared_naming_term"
    )
    assert issue["token"] == "neon"
    assert issue["count"] == 5
    assert issue["entity_ratio"] == 0.625
    assert issue["topic_count"] == 4
    assert len(issue["occurrences"]) == 5


def test_exactly_half_the_world_does_not_exceed_budget() -> None:
    names = _dominant_names()
    names[4] = ("ent:5", "Ivory Trestle")

    report = naming_portfolio_report(_portfolio(names), {})

    assert report["passed"] is True


def test_generic_category_suffixes_are_ignored() -> None:
    rows = _portfolio(
        [
            ("ent:1", "Amber District"),
            ("ent:2", "Copper District"),
            ("ent:3", "Glass District"),
            ("ent:4", "Ivory District"),
            ("ent:5", "Lantern District"),
            ("ent:6", "Mirror District"),
            ("ent:7", "Thorn District"),
            ("ent:8", "Violet District"),
        ]
    )

    report = naming_portfolio_report(rows, {})

    assert report["passed"] is True
    assert all(issue["token"] != "district" for issue in report["issues"])


def test_declared_naming_family_exempts_exact_members_only() -> None:
    rows = _portfolio(_dominant_names())
    family_members = [f"ent:{index}" for index in range(1, 6)]
    graph = {
        "metadata": {
            "naming_families": [
                {
                    "family_id": "family:neon-civic",
                    "terms": ["Neon"],
                    "entity_ids": family_members,
                }
            ]
        }
    }

    report = naming_portfolio_report(rows, graph)

    assert report["passed"] is True
    assert report["declared_families"][0]["family_id"] == "family:neon-civic"


def test_repeated_acronym_over_half_the_world_is_blocking() -> None:
    rows = _portfolio(
        [
            ("ent:1", "AFS Meridian"),
            ("ent:2", "AFS Relay"),
            ("ent:3", "AFS Bastion"),
            ("ent:4", "AFS Trestle"),
            ("ent:5", "Amber Reach"),
            ("ent:6", "Copper Vale"),
        ]
    )

    issues = naming_portfolio_issues(rows, {})

    assert any(
        issue.code == "dominant_undeclared_acronym" and issue.token == "AFS"
        for issue in issues
    )


def test_acronym_density_and_unique_budgets_are_both_enforced() -> None:
    rows = _portfolio(
        [
            ("ent:1", "AFS Meridian"),
            ("ent:2", "BCD Relay"),
            ("ent:3", "CEN Bastion"),
            ("ent:4", "DOR Trestle"),
            ("ent:5", "EVA Orchard"),
            ("ent:6", "Amber Reach"),
            ("ent:7", "Copper Vale"),
            ("ent:8", "Glass Harbor"),
            ("ent:9", "Ivory Ward"),
            ("ent:10", "Lantern Bridge"),
        ]
    )

    codes = {issue.code for issue in naming_portfolio_issues(rows, {})}

    assert "acronym_entity_budget_exceeded" in codes
    assert "unique_acronym_budget_exceeded" in codes


def test_generic_ai_acronym_is_not_charged_to_budget() -> None:
    rows = _portfolio(
        [
            ("ent:1", "AI Meridian"),
            ("ent:2", "AI Trestle"),
            ("ent:3", "Amber Reach"),
            ("ent:4", "Copper Vale"),
            ("ent:5", "Glass Orchard"),
            ("ent:6", "Ivory Ward"),
            ("ent:7", "Lantern Bridge"),
            ("ent:8", "Mirror Quay"),
        ]
    )

    report = naming_portfolio_report(rows, {})

    assert report["passed"] is True
    assert report["checks"]["tracked_acronym_count"] == 0


def test_policy_override_can_support_an_acronym_heavy_profile() -> None:
    rows = _portfolio(
        [
            ("ent:1", "AFS Meridian"),
            ("ent:2", "BCD Relay"),
            ("ent:3", "CEN Bastion"),
            ("ent:4", "DOR Trestle"),
            ("ent:5", "Amber Reach"),
            ("ent:6", "Copper Vale"),
            ("ent:7", "Glass Harbor"),
            ("ent:8", "Ivory Ward"),
        ]
    )
    graph = {
        "metadata": {
            "naming_portfolio_policy": {
                "maximum_acronym_entity_ratio": 0.6,
                "maximum_unique_acronym_ratio": 0.6,
            }
        }
    }

    report = naming_portfolio_report(rows, graph)

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

    with pytest.raises(NamingPortfolioCompilationError):
        generation_compilation.compile_world_generation_certified_artifact(
            run={"run_id": "run:1", "graph": {}},
            world={"id": "world:1"},
            topic_rows=_portfolio(_dominant_names()),
            revision=1,
        )

    assert called is False


def test_diagnostic_compilation_retains_naming_report(
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
        topic_rows=_portfolio(_dominant_names()),
        revision=1,
    )

    report = artifact.certification["naming_portfolio"]
    assert report["passed"] is False
    assert artifact.certification["launch_ready"] is False
    assert "naming_portfolio" in artifact.certification["missing_requirements"]


def test_publication_transaction_surfaces_naming_failure() -> None:
    report = publication_transaction_report(
        {
            "run_id": "run:1",
            "world_id": "world:1",
            "status": "review",
            "progress": {"publication_blocked": False},
        },
        {
            "launch_ready": False,
            "missing_requirements": ["naming_portfolio"],
            "naming_portfolio": {
                "passed": False,
                "issues": [{"code": "dominant_undeclared_naming_term"}],
            },
        },
    )

    assert report["publishable"] is False
    assert "naming_portfolio" in report["failed_reports"]
