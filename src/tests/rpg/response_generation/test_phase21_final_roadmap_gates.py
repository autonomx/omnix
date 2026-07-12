from __future__ import annotations

from app.rpg.presentation.dialogue_quality_benchmark import (
    build_provider_free_dialogue_matrix,
    evaluate_dialogue_quality_matrix,
)
from app.rpg.release_gates import (
    evaluate_dialogue_quality_release_gates,
    evaluate_migration_release_gates,
    evaluate_performance_release_gates,
    evaluate_ui_timing_release_gates,
)
from app.rpg.session.migrations import migrate_session_payload


def test_dialogue_quality_report_passes_permanent_release_gate() -> None:
    benchmark = evaluate_dialogue_quality_matrix(build_provider_free_dialogue_matrix())
    gate = evaluate_dialogue_quality_release_gates(benchmark)

    assert benchmark["ok"] is True
    assert gate["ok"] is True, gate
    assert gate["accepted_case_count"] >= 30


def test_near_duplicate_rate_must_be_strictly_below_five_percent() -> None:
    report = {
        "accepted_case_count": 30,
        "failures": [],
        "metrics": {
            "direct_answer_rate": 1.0,
            "correct_speaker_rate": 1.0,
            "grounded_specificity_rate": 1.0,
            "continuity_rate": 1.0,
            "candidate_rejection_rate": 1.0,
            "near_duplicate_rate": 0.05,
            "private_leak_rate": 0.0,
            "empty_line_rate": 0.0,
        },
    }

    gate = evaluate_dialogue_quality_release_gates(report)

    assert gate["ok"] is False
    assert "near_duplicate_rate_above_target" in gate["failures"]


def test_performance_gate_requires_95_percent_attribution_and_50kb_response() -> None:
    passing = evaluate_performance_release_gates(
        {
            "total_ms": 100.0,
            "unattributed_ms": 4.0,
            "attribution_percent": 96.0,
            "cpu_ms": 30.0,
            "response_bytes": 20_000,
        }
    )
    failing = evaluate_performance_release_gates(
        {
            "total_ms": 100.0,
            "unattributed_ms": 8.0,
            "attribution_percent": 92.0,
            "cpu_ms": 30.0,
            "response_bytes": 60_000,
        }
    )

    assert passing["ok"] is True
    assert failing["ok"] is False
    assert "foreground_attribution_below_95_percent" in failing["failures"]
    assert "response_exceeds_50kb" in failing["failures"]


def test_ui_gate_requires_identity_and_commit_to_visible_under_50ms() -> None:
    passing = evaluate_ui_timing_release_gates(
        {
            "interactionId": "interaction:12",
            "client": {
                "commitToVisibleMs": 18.5,
                "requestToVisibleMs": 824.0,
            },
        }
    )
    zero_millisecond = evaluate_ui_timing_release_gates(
        {
            "interactionId": "interaction:13",
            "client": {
                "commitToVisibleMs": 0.0,
                "requestToVisibleMs": 0.0,
            },
        }
    )
    failing = evaluate_ui_timing_release_gates(
        {
            "interactionId": "",
            "client": {"commitToVisibleMs": 55.0},
        }
    )

    assert passing["ok"] is True
    assert zero_millisecond["ok"] is True
    assert zero_millisecond["commit_to_visible_ms"] == 0.0
    assert zero_millisecond["request_to_visible_ms"] == 0.0
    assert failing["ok"] is False
    assert "missing_ui_interaction_identity" in failing["failures"]
    assert "react_commit_to_visible_above_50ms" in failing["failures"]


def test_migrated_session_passes_migration_release_gate() -> None:
    session = migrate_session_payload(
        {
            "manifest": {"id": "session:gate", "schema_version": 4},
            "runtime_state": {
                "transcript": [
                    "You: What did you see?",
                    "Bran: A rider took the north road before dawn.",
                ]
            },
        }
    )

    gate = evaluate_migration_release_gates(session)

    assert gate["ok"] is True, gate
    assert gate["schema_version"] == 5
    assert gate["interaction_count"] == 1
    assert gate["interaction_seq"] == 1
