from __future__ import annotations

from app.gateway.live_chat_release_gate import (
    DEFAULT_LIVE_CHAT_METRIC_POLICIES,
    LiveChatEvidenceBundle,
    LiveChatEvidenceMetadata,
    LiveChatMetricPolicy,
    LiveChatReleaseThresholds,
    evaluate_live_chat_release_gate_bundles,
)


def _metadata(character_id: str, **changes) -> LiveChatEvidenceMetadata:
    payload = {
        "exact_commit_sha": "a" * 40,
        "browser_version": "Chrome 150",
        "os_version": "Windows 11",
        "input_device_hash": "input-device-hash",
        "output_device_hash": "output-device-hash",
        "character_id": character_id,
        "profile_version": 4,
        "presence_preset": "natural",
        "configured_duplex_mode": "automatic",
        "resolved_duplex_mode": "echo_aware",
        "calibration_version": "cal-v1",
    }
    payload.update(changes)
    return LiveChatEvidenceMetadata.model_validate(payload)


def _thresholds() -> LiveChatReleaseThresholds:
    return LiveChatReleaseThresholds(
        required_scenarios=("normal-user-turn",),
        metric_policies={
            name: LiveChatMetricPolicy(
                kind=policy.kind,
                limit=policy.limit,
                comparison=policy.comparison,
                minimum_samples=2,
            )
            for name, policy in DEFAULT_LIVE_CHAT_METRIC_POLICIES.items()
        },
    )


def _passing_value(name: str) -> float:
    if name in {
        "natural_eos_rate",
        "proactive_prompt_acceptance_rate",
        "conversation_repair_success_rate",
    }:
        return 1.0
    if name == "perceived_listening_score":
        return 5.0
    if name == "perceived_pressure_score":
        return 1.0
    if name.endswith("_ms"):
        return 100.0
    return 0.0


def _bundle(character_id: str, suffix: str) -> LiveChatEvidenceBundle:
    return LiveChatEvidenceBundle(
        metadata=_metadata(character_id),
        events=[{
            "trace_id": f"trace-{suffix}-{name}",
            "scenario": "normal-user-turn",
            "metric_name": name,
            "value": _passing_value(name),
            "character_id": character_id,
        } for name in DEFAULT_LIVE_CHAT_METRIC_POLICIES],
    )


def test_release_gate_aggregates_system_and_character_bundles() -> None:
    report = evaluate_live_chat_release_gate_bundles(
        [_bundle("system-assistant", "system"), _bundle("maya", "character")],
        thresholds=_thresholds(),
    )

    assert report.status == "pass"
    assert report.character_modes == ["character", "system"]
    assert len(report.metadata_records) == 2
    assert all(metric.status == "pass" for metric in report.metrics)


def test_release_gate_fails_closed_on_unknown_runtime_identity() -> None:
    bundle = _bundle("system-assistant", "system")
    bundle = bundle.model_copy(update={
        "metadata": _metadata("system-assistant", browser_version="unknown"),
    })
    report = evaluate_live_chat_release_gate_bundles(
        [bundle, _bundle("maya", "character")],
        thresholds=_thresholds(),
    )

    assert report.status == "insufficient"
    assert any("browser_version" in reason for reason in report.insufficient)
