from __future__ import annotations

from app.rpg.local_acceptance import evaluate_local_acceptance_bundle
from app.rpg.local_live_smoke import evaluate_live_smoke_payload
from app.rpg.presentation.dialogue_quality_benchmark import (
    build_provider_free_dialogue_matrix,
    evaluate_dialogue_quality_matrix,
)
from app.rpg.release_finalization import local_live_acceptance_criteria


def _live_smoke_report() -> dict:
    return {
        "format_version": "rpg_interactive_live_smoke_v2",
        "ok": True,
        "failures": [],
        "distinct_interaction_count": 3,
        "latency_seconds": {"median": 1.2, "p95": 2.1},
        "runtime_evidence": {
            "provider_call_counts": [1, 1, 1],
            "non_provider_overhead_ms": [80.0, 91.0, 75.0],
            "server_attribution_percent": [98.0, 97.0, 99.0],
        },
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
    dialogue = evaluate_dialogue_quality_matrix(build_provider_free_dialogue_matrix())
    report = evaluate_local_acceptance_bundle(
        live_smoke_report=_live_smoke_report(),
        dialogue_quality_report=dialogue,
        browser_timing_samples=_browser_samples(),
    )

    assert report["ok"] is True, report
    assert report["failures"] == []
    assert report["browser_timing"]["sample_count"] == 3
    assert report["browser_timing"]["maximum_commit_to_visible_ms"] == 24.0


def test_local_acceptance_bundle_rejects_missing_or_slow_browser_evidence() -> None:
    dialogue = evaluate_dialogue_quality_matrix(build_provider_free_dialogue_matrix())
    report = evaluate_local_acceptance_bundle(
        live_smoke_report=_live_smoke_report(),
        dialogue_quality_report=dialogue,
        browser_timing_samples=[
            {"interactionId": "interaction:1", "client": {"commitToVisibleMs": 55.0}},
        ],
    )

    assert report["ok"] is False
    assert "insufficient_browser_timing_samples" in report["failures"]
    assert "browser_visibility_timing_failed" in report["failures"]


def test_live_payload_extracts_provider_call_and_provider_time_without_calling_model() -> None:
    payload = {
        "ok": True,
        "contract_version": "rpg_turn_response_v2",
        "interaction_id": "interaction:1",
        "visible_response": {
            "narration": "Bran considers the question.",
            "messages": [{"kind": "npc_dialogue", "speaker": "Bran", "text": "Business is steady."}],
            "plain_text": "Bran: Business is steady.",
        },
        "result": {
            "llm_called": True,
            "timing": {"provider_ms": 700.0},
        },
        "state": {"changed_domains": ["conversation"]},
    }

    report = evaluate_live_smoke_payload(payload)

    assert report["ok"] is True
    assert report["provider_call_count"] == 1
    assert report["provider_ms"] == 700.0


def test_local_acceptance_criteria_include_original_full_targets() -> None:
    criteria = local_live_acceptance_criteria()

    assert criteria["target_median_seconds"] == 1.5
    assert criteria["target_p95_seconds"] == 2.5
    assert criteria["required_dialogue_provider_calls"] == 1
    assert criteria["minimum_foreground_attribution_percent"] == 95.0
    assert criteria["maximum_http_overhead_ms"] == 250.0
    assert criteria["maximum_browser_commit_visible_ms"] == 50.0
    assert criteria["dialogue_quality_minimums"]["correct_speaker_rate"] == 0.99
    assert criteria["dialogue_quality_maximums"]["private_leak_rate"] == 0.0
