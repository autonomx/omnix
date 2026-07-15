from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.desktop_companion.evaluation import (
    DesktopCompanionEvaluationCreate,
    DesktopCompanionEvaluationStore,
    build_desktop_companion_release_gate,
    hash_vision_model_id,
    resolve_desktop_companion_rollout,
)


SCENARIOS = (
    "static-screen",
    "typing",
    "rapid-browsing",
    "scene-change",
    "interruption",
    "screen-prompt-injection",
)


def create(index: int, *, stage: str = "shadow", scenario: str | None = None, **updates):
    values = {
        "run_id": f"run-{index}",
        "session_id": f"chat-{index}",
        "started_at": f"2026-07-14T12:0{index}:00Z",
        "ended_at": f"2026-07-14T12:0{index}:30Z",
        "exact_commit_sha": "94a179154dc98f6e455c604bed100c0beee06046",
        "rollout_stage": stage,
        "vision_provider": "lmstudio",
        "vision_model_hash": hash_vision_model_id("qwen2.5-vl"),
        "counts": {"max_vision_calls_per_minute": 6, "observations": 20},
        "latency_ms": {"observation_p95": 4_500},
        "rates": {
            "stale_output_rate": 0.0,
            "duplicate_comment_rate": 0.0,
            "unsupported_claim_rate": 0.0,
            "collision_rate": 0.0,
            "provider_error_rate": 0.0,
        },
        "scenario_labels": [scenario or SCENARIOS[index % len(SCENARIOS)]],
    }
    values.update(updates)
    return DesktopCompanionEvaluationCreate(**values)


def test_evaluation_store_upserts_content_free_records(tmp_path: Path):
    store = DesktopCompanionEvaluationStore(tmp_path / "desktop-evaluations.json")
    first = store.upsert(create(0))
    updated = store.upsert(create(0, counts={"max_vision_calls_per_minute": 5}))

    assert first.evaluation_id == updated.evaluation_id
    assert updated.counts["max_vision_calls_per_minute"] == 5
    assert len(store.list()) == 1
    assert store.export()["evaluations"][0]["vision_model_hash"] == hash_vision_model_id("qwen2.5-vl")


def test_evaluation_rejects_content_bearing_metric_keys():
    with pytest.raises(ValidationError, match="content-bearing"):
        create(0, rates={"screen_text_rate": 0.0})
    with pytest.raises(ValidationError, match="content-bearing"):
        create(0, counts={"raw_image_count": 1})


def test_release_gate_passes_complete_bounded_evidence():
    records = [
        DesktopCompanionEvaluationStore(Path("unused")).upsert(create(index, scenario=scenario))
        for index, scenario in enumerate(SCENARIOS)
    ]
    report = build_desktop_companion_release_gate(records)

    assert report.status == "pass"
    assert report.missing_scenarios == ()
    assert all(metric.status == "pass" for metric in report.metrics)
    assert len(report.evidence_evaluation_ids) == len(SCENARIOS)


def test_release_gate_fails_unsafe_rates_and_limits():
    store = DesktopCompanionEvaluationStore(Path("unused-fail"))
    records = [store.upsert(create(index, scenario=scenario)) for index, scenario in enumerate(SCENARIOS)]
    unsafe = records[0].model_copy(
        update={
            "rates": {**records[0].rates, "unsupported_claim_rate": 0.2},
            "counts": {**records[0].counts, "max_vision_calls_per_minute": 9},
        }
    )
    report = build_desktop_companion_release_gate([unsafe, *records[1:]])

    assert report.status == "fail"
    assert "unsupported_claim_rate" in report.failures
    assert "max_vision_calls_per_minute" in report.failures


def test_rollout_degrades_text_and_speech_until_evidence_passes():
    insufficient = build_desktop_companion_release_gate([])
    text = resolve_desktop_companion_rollout("text", insufficient)
    speech = resolve_desktop_companion_rollout("speech", insufficient)

    assert text.effective_stage == "shadow"
    assert text.reason == "release_gate_requires_shadow"
    assert speech.effective_stage == "shadow"

    store = DesktopCompanionEvaluationStore(Path("unused-speech"))
    records = [store.upsert(create(index, scenario=scenario)) for index, scenario in enumerate(SCENARIOS)]
    passed = build_desktop_companion_release_gate(records)
    assert resolve_desktop_companion_rollout("text", passed).effective_stage == "text"
    assert resolve_desktop_companion_rollout("speech", passed).effective_stage == "text"

    speech_records = [records[0].model_copy(update={"rollout_stage": "speech"}), *records[1:]]
    speech_passed = build_desktop_companion_release_gate(speech_records)
    assert resolve_desktop_companion_rollout("speech", speech_passed).effective_stage == "speech"
