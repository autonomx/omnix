from __future__ import annotations

from fastapi.testclient import TestClient

from app.gateway.live_chat_release_gate import (
    DEFAULT_LIVE_CHAT_METRIC_POLICIES,
    REQUIRED_LIVE_CHAT_SCENARIOS,
    LiveChatEvidenceMetadata,
    LiveChatMetricPolicy,
    LiveChatReleaseThresholds,
    evaluate_live_chat_release_gate,
)
from app.gateway.main import create_gateway_app


class EmptyJobStore:
    def list_events(self, after_id: int, limit: int):
        return []


def _metadata(**changes):
    payload = {
        "exact_commit_sha": "a" * 40,
        "browser_version": "Chrome 150",
        "os_version": "Windows 11",
        "input_device_hash": "input-device-hash",
        "output_device_hash": "output-device-hash",
        "character_id": "maya",
        "profile_version": 4,
        "presence_preset": "natural",
        "configured_duplex_mode": "automatic",
        "resolved_duplex_mode": "echo_aware",
        "calibration_version": "cal-v1",
    }
    payload.update(changes)
    return LiveChatEvidenceMetadata.model_validate(payload)


def _thresholds(required_scenarios=("normal-user-turn",), minimum_samples=2):
    policies = {
        name: LiveChatMetricPolicy(
            kind=policy.kind,
            limit=policy.limit,
            comparison=policy.comparison,
            minimum_samples=minimum_samples,
        )
        for name, policy in DEFAULT_LIVE_CHAT_METRIC_POLICIES.items()
    }
    return LiveChatReleaseThresholds(
        required_scenarios=required_scenarios,
        metric_policies=policies,
        require_system_and_character=False,
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


def _passing_events(samples: int = 2):
    events = []
    for name in DEFAULT_LIVE_CHAT_METRIC_POLICIES:
        for index in range(samples):
            events.append({
                "timestamp_utc": "2026-07-11T12:00:00+00:00",
                "trace_id": f"trace-{index}",
                "scenario": "normal-user-turn",
                "metric_name": name,
                "value": _passing_value(name),
            })
    return events


def test_phase9_gate_passes_complete_content_free_evidence() -> None:
    report = evaluate_live_chat_release_gate(
        _metadata(),
        _passing_events(),
        thresholds=_thresholds(),
    )

    assert report.status == "pass"
    assert report.missing_scenarios == []
    assert report.failures == []
    assert report.insufficient == []
    assert report.metadata.input_device_hash == "input-device-hash"
    assert all(metric.status == "pass" for metric in report.metrics)


def test_phase9_gate_fails_nonnegotiable_echo_submission_metric() -> None:
    events = _passing_events()
    for event in events:
        if event["metric_name"] == "playback_echo_submission_rate":
            event["value"] = 1.0

    report = evaluate_live_chat_release_gate(
        _metadata(),
        events,
        thresholds=_thresholds(),
    )

    assert report.status == "fail"
    assert any("playback_echo_submission_rate" in failure for failure in report.failures)


def test_phase9_gate_never_passes_missing_hardware_scenarios() -> None:
    report = evaluate_live_chat_release_gate(
        _metadata(),
        _passing_events(),
        thresholds=_thresholds(required_scenarios=REQUIRED_LIVE_CHAT_SCENARIOS),
    )

    assert report.status == "insufficient"
    assert "normal-user-turn" not in report.missing_scenarios
    assert "pure-assistant-echo" in report.missing_scenarios
    assert "sustained-20-minute-conversation" in report.missing_scenarios


def test_phase9_route_rejects_transcript_or_audio_payload_fields() -> None:
    app = create_gateway_app(job_store_factory=lambda: EmptyJobStore())
    client = TestClient(app)
    payload = {
        "metadata": _metadata().model_dump(mode="json"),
        "events": [{
            **_passing_events(samples=1)[0],
            "transcript": "private words",
        }],
        "thresholds": _thresholds(minimum_samples=1).model_dump(mode="json"),
    }

    response = client.post(
        "/api/tts/live-call/diagnostics/release-gate/v2/evaluate",
        json=payload,
    )

    assert response.status_code == 422


def test_phase9_route_evaluates_reproducible_runtime_evidence() -> None:
    app = create_gateway_app(job_store_factory=lambda: EmptyJobStore())
    client = TestClient(app)

    response = client.post(
        "/api/tts/live-call/diagnostics/release-gate/v2/evaluate",
        json={
            "metadata": _metadata().model_dump(mode="json"),
            "events": _passing_events(),
            "thresholds": _thresholds().model_dump(mode="json"),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "pass"
    assert payload["metadata"]["exact_commit_sha"] == "a" * 40
    assert len(payload["metrics"]) == len(DEFAULT_LIVE_CHAT_METRIC_POLICIES)
