from __future__ import annotations

from app.desktop_companion.evaluation import DesktopCompanionEvaluationRecord, hash_vision_model_id
from app.desktop_companion.release_gate import (
    DesktopCompanionEvidencePartition,
    build_partitioned_desktop_companion_release_gate,
    build_partitioned_desktop_companion_speech_gate,
    desktop_companion_speech_canary_enabled,
    select_desktop_companion_evidence,
)

SCENARIOS = (
    "static-screen",
    "typing",
    "rapid-browsing",
    "scene-change",
    "interruption",
    "screen-prompt-injection",
)
SPEECH_SCENARIOS = (*SCENARIOS, "speech-completed", "speech-stale")


def record(
    index: int,
    *,
    commit: str = "abcdef0123456789",
    model: str = "model-a",
    stage: str = "shadow",
    speech: bool = False,
) -> DesktopCompanionEvaluationRecord:
    scenarios = SPEECH_SCENARIOS if speech else SCENARIOS
    return DesktopCompanionEvaluationRecord(
        run_id=f"run:{commit}:{stage}:{index}",
        session_id=f"chat:{index}",
        started_at="2026-07-15T00:00:00Z",
        ended_at="2026-07-15T00:01:00Z",
        exact_commit_sha=commit,
        app_version="1.0.0",
        browser_version="test",
        os_version="test",
        character_id="system-assistant",
        observation_schema_version=1,
        attention_policy_version=1,
        rollout_stage=stage,
        vision_provider="openai-compatible-local",
        vision_model_hash=hash_vision_model_id(model),
        remote_provider=False,
        counts={
            "max_vision_calls_per_minute": 6,
            "observations": 20,
            "deliveries": 1 if speech else 0,
        },
        latency_ms={"observation_p95": 4_000},
        rates={
            "stale_output_rate": 0.0,
            "duplicate_comment_rate": 0.0,
            "unsupported_claim_rate": 0.0,
            "collision_rate": 0.0,
            "provider_error_rate": 0.0,
        },
        scenario_labels=[scenarios[index % len(scenarios)]],
        evaluation_id=f"eval:{commit}:{stage}:{index}",
        created_at="2026-07-15T00:01:00Z",
        updated_at="2026-07-15T00:01:00Z",
    )


def partition() -> DesktopCompanionEvidencePartition:
    return DesktopCompanionEvidencePartition(
        exact_commit_sha="abcdef0123456789",
        observation_schema_version=1,
        attention_policy_version=1,
        vision_provider="openai-compatible-local",
        vision_model_hash=hash_vision_model_id("model-a"),
        remote_provider=False,
    )


def test_release_gate_uses_one_exact_evidence_partition() -> None:
    matching = [record(index) for index in range(12)]
    mixed = [
        record(20, commit="ffffffffffffffff"),
        record(21, model="model-b"),
    ]

    selected = select_desktop_companion_evidence([*matching, *mixed], partition())
    report = build_partitioned_desktop_companion_release_gate([*matching, *mixed], partition())

    assert len(selected) == 12
    assert report.status == "pass"
    assert report.records_scanned == 12
    assert report.exact_commit_shas == ("abcdef0123456789",)


def test_partition_gate_requires_twelve_records_and_exact_build() -> None:
    insufficient = build_partitioned_desktop_companion_release_gate(
        [record(index) for index in range(6)],
        partition(),
    )
    unknown = build_partitioned_desktop_companion_release_gate(
        [record(index, commit="unknown-local-build") for index in range(12)],
        DesktopCompanionEvidencePartition(exact_commit_sha="unknown-local-build"),
    )

    assert insufficient.status == "insufficient"
    assert "minimum_partition_records:6/12" in insufficient.insufficient
    assert unknown.status == "insufficient"
    assert "exact_build_identity_required" in unknown.insufficient


def test_speech_gate_requires_speech_records_deliveries_and_scenarios() -> None:
    passing = [record(index, stage="speech", speech=True) for index in range(24)]
    report = build_partitioned_desktop_companion_speech_gate(passing, partition())
    insufficient = build_partitioned_desktop_companion_speech_gate(
        [record(index, stage="speech", speech=True) for index in range(6)],
        partition(),
    )

    assert report.status == "pass"
    assert report.rollout_stages == ("speech",)
    assert insufficient.status == "insufficient"
    assert "minimum_speech_records:6/12" in insufficient.insufficient
    assert "minimum_speech_deliveries:6/12" in insufficient.insufficient


def test_speech_canary_is_explicit_and_default_off() -> None:
    assert desktop_companion_speech_canary_enabled({}) is False
    assert desktop_companion_speech_canary_enabled({"OMNIX_DESKTOP_COMPANION_SPEECH_CANARY": "true"}) is True
    assert desktop_companion_speech_canary_enabled({"OMNIX_DESKTOP_COMPANION_SPEECH_CANARY": "0"}) is False
