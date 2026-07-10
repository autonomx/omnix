from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.gateway.live_voice_release_gate import (
    REQUIRED_LIVE_VOICE_SCENARIOS,
    LiveVoiceReleaseThresholds,
    evaluate_live_voice_log,
    evaluate_live_voice_release_gate,
)
from app.gateway.main import create_gateway_app


class EmptyJobStore:
    def list_events(self, after_id: int, limit: int):
        return []


def _passing_events(samples: int = 5, trials: int = 10):
    events = []
    for index in range(samples):
        for name, value in (
            ("stt_finalize_ms", 400 + index),
            ("final_to_first_token_ms", 900 + index),
            ("first_token_to_first_audio_ms", 600 + index),
            ("interruption_to_silence_ms", 180 + index),
        ):
            events.append({
                "event": "release_metric",
                "trace_id": f"trace:{index}",
                "metric_name": name,
                "value_ms": value,
                "scenario": "system-normal",
            })
    for name in (
        "false_interruption",
        "missed_interruption",
        "backchannel_false_positive",
    ):
        for index in range(trials):
            events.append({
                "event": "release_quality",
                "trace_id": f"quality:{index}",
                "quality_name": name,
                "occurred": False,
                "scenario": "system-normal",
            })
    return events


def _single_scenario_thresholds(**changes):
    return LiveVoiceReleaseThresholds(
        required_scenarios=("system-normal",),
        **changes,
    )


def test_release_gate_passes_complete_bounded_evidence() -> None:
    report = evaluate_live_voice_release_gate(
        _passing_events(),
        thresholds=_single_scenario_thresholds(),
    )

    assert report.status == "pass"
    assert report.failures == []
    assert report.insufficient == []
    assert report.scenarios == ["system-normal"]
    assert report.missing_scenarios == []
    assert all(metric.status == "pass" for metric in report.metrics)


def test_release_gate_fails_latency_and_quality_thresholds() -> None:
    events = _passing_events()
    events.extend({
        "event": "release_metric",
        "trace_id": f"slow:{index}",
        "metric_name": "interruption_to_silence_ms",
        "value_ms": 900,
        "scenario": "system-normal",
    } for index in range(5))
    events.extend({
        "event": "release_quality",
        "trace_id": f"false:{index}",
        "quality_name": "false_interruption",
        "occurred": True,
        "scenario": "system-normal",
    } for index in range(2))

    report = evaluate_live_voice_release_gate(
        events,
        thresholds=_single_scenario_thresholds(),
    )

    assert report.status == "fail"
    assert any("interruption_to_silence_ms" in failure for failure in report.failures)
    assert any("false_interruption" in failure for failure in report.failures)


def test_release_gate_reports_insufficient_evidence_without_guessing() -> None:
    report = evaluate_live_voice_release_gate([
        {
            "event": "release_metric",
            "trace_id": "trace:1",
            "metric_name": "stt_finalize_ms",
            "value_ms": 300,
        }
    ])

    assert report.status == "insufficient"
    assert report.failures == []
    assert len(report.insufficient) == 8
    assert set(report.missing_scenarios) == set(REQUIRED_LIVE_VOICE_SCENARIOS)


def test_release_gate_requires_the_complete_runtime_scenario_matrix() -> None:
    report = evaluate_live_voice_release_gate(_passing_events())

    assert report.status == "insufficient"
    assert "system-normal" not in report.missing_scenarios
    assert "character-normal" in report.missing_scenarios
    assert "rapid-interruption-soak" in report.missing_scenarios


def test_release_gate_reads_jsonl_and_ignores_invalid_records(tmp_path) -> None:
    path = tmp_path / "live-call-streaming.log"
    now = datetime.now(timezone.utc).isoformat()
    records = [dict(event, timestamp_utc=now) for event in _passing_events()]
    path.write_text(
        "not-json\n" + "\n".join(json.dumps(record) for record in records),
        encoding="utf-8",
    )

    report = evaluate_live_voice_log(
        path,
        hours=24,
        thresholds=_single_scenario_thresholds(),
    )

    assert report.status == "pass"
    assert report.records_scanned == len(records)


def test_release_gate_route_evaluates_supplied_evidence() -> None:
    app = create_gateway_app(job_store_factory=lambda: EmptyJobStore())
    client = TestClient(app)

    response = client.post(
        "/api/tts/live-call/diagnostics/release-gate/evaluate",
        json={
            "events": _passing_events(samples=2, trials=2),
            "thresholds": {
                "minimum_latency_samples": 2,
                "minimum_quality_trials": 2,
                "required_scenarios": ["system-normal"],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "pass"
    assert len(payload["metrics"]) == 7


def test_release_gate_route_reads_current_log(monkeypatch, tmp_path) -> None:
    from app.gateway import live_voice_diagnostics_routes

    path = tmp_path / "live-call-streaming.log"
    path.write_text("", encoding="utf-8")
    monkeypatch.setattr(live_voice_diagnostics_routes, "diagnostics_log_path", lambda: str(path))
    app = create_gateway_app(job_store_factory=lambda: EmptyJobStore())
    client = TestClient(app)

    response = client.get(
        "/api/tts/live-call/diagnostics/release-gate",
        params={"minimum_latency_samples": 1, "minimum_quality_trials": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "insufficient"
    assert set(payload["missing_scenarios"]) == set(REQUIRED_LIVE_VOICE_SCENARIOS)
