from __future__ import annotations

from app.rpg.dialogue_quality_benchmark import run_dialogue_quality_benchmark
from app.rpg.local_acceptance import evaluate_local_acceptance_bundle
from app.rpg.release_finalization import local_live_acceptance_criteria
from app.rpg.release_gates import evaluate_ui_timing_release_gates


def _live_smoke_report() -> dict:
    return {
        "format_version": "rpg_interactive_live_smoke_v1",
        "ok": True,
        "failures": [],
        "distinct_interaction_count": 3,
        "latency_seconds": {"median": 1.2, "p95": 2.1},
    }


def _browser_samples() -> list[dict]:
    return [
        {
            "interactionId": f"interaction:{index}",
            "client": {
                "commitToVisibleMs": value,
                "requestToVisibleMs": 1000.0 + value,
            },
        }
        for index, value in enumerate((12.0, 18.0, 24.0), start=1)
    ]


def test_local_acceptance_bundle_requires_all_three_evidence_surfaces() -> None:
    report = evaluate_local_acceptance_bundle(
        live_smoke_report=_live_smoke_report(),
        dialogue_quality_report=run_dialogue_quality_benchmark(),
        browser_timing_samples=_browser_samples(),
    )

    assert report["ok"] is True, report
    assert report["failures"] == []
    assert report["browser_timing"]["sample_count"] == 3
    assert report["browser_timing"]["maximum_commit_to_visible_ms"] == 24.0


def test_local_acceptance_bundle_rejects_missing_or_slow_browser_evidence() -> None:
    report = evaluate_local_acceptance_bundle(
        live_smoke_report=_live_smoke_report(),
        dialogue_quality_report=run_dialogue_quality_benchmark(),
        browser_timing_samples=[
            {"interactionId": "interaction:1", "client": {"commitToVisibleMs": 55.0}},
        ],
    )

    assert report["ok"] is False
    assert "insufficient_browser_timing_samples" in report["failures"]
    assert "browser_visibility_timing_failed" in report["failures"]
    assert "browser:0:react_commit_to_visible_above_50ms" in report["failures"]


def test_ui_timing_gate_accepts_snake_case_export_shape() -> None:
    report = evaluate_ui_timing_release_gates(
        {
            "interaction_id": "interaction:7",
            "commit_to_visible_ms": 21.5,
            "request_to_visible_ms": 900.0,
        }
    )

    assert report["ok"] is True
    assert report["interaction_id"] == "interaction:7"
    assert report["commit_to_visible_ms"] == 21.5


def test_local_acceptance_criteria_include_browser_visibility_target() -> None:
    criteria = local_live_acceptance_criteria()

    assert criteria["target_median_seconds"] == 1.5
    assert criteria["target_p95_seconds"] == 2.5
    assert criteria["maximum_browser_commit_visible_ms"] == 50.0
