from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.gateway.live_chat_evaluation_store import (
    LiveChatEvaluationStore,
    PresencePolicyValues,
    PresencePolicyVersionCreate,
    VoiceSessionEvaluationCreate,
)
from app.gateway.main import create_gateway_app


class EmptyJobStore:
    def list_events(self, after_id: int, limit: int):
        return []


def _create(
    call_id: str = "call-one",
    *,
    character_id: str = "maya",
    scenario_labels: list[str] | None = None,
) -> VoiceSessionEvaluationCreate:
    return VoiceSessionEvaluationCreate(
        call_id=call_id,
        session_id="chat:maya",
        started_at="2026-07-11T12:00:00+00:00",
        ended_at="2026-07-11T12:10:00+00:00",
        exact_commit_sha="a" * 40,
        app_version="1.2.3",
        browser_version="Chrome 150.0.0",
        os_version="Windows 11 24H2",
        character_id=character_id,
        profile_version=4,
        presence_preset="natural",
        conversation_stance="discuss",
        configured_duplex_mode="automatic",
        resolved_duplex_mode="echo_aware",
        calibration_version="live-voice-calibration-v1",
        input_device_hash="input-device-hash",
        output_device_hash="output-device-hash",
        environment_hash="environment-hash",
        latency_summary={
            "stt_finalize_p95_ms": 500.0,
            "final_to_first_token_p95_ms": 900.0,
            "first_token_to_first_audio_p95_ms": 400.0,
            "interruption_to_silence_p95_ms": 180.0,
            "cancellation_p95_ms": 180.0,
            "rejected_candidate_restore_p95_ms": 120.0,
        },
        quality_metrics={
            "false_barge_in_rate": 0.0,
            "missed_barge_in_rate": 0.0,
            "playback_echo_submission_rate": 0.0,
            "interruption_success_rate": 1.0,
            "proactive_acceptance_rate": 0.8,
            "silence_fill_regret_rate": 0.0,
            "backchannel_collision_rate": 0.0,
            "repair_success_rate": 1.0,
            "repeated_topic_rate": 0.0,
            "unanswered_obligation_rate": 0.0,
            "perceived_listening_score": 5.0,
            "perceived_pressure_score": 1.0,
        },
        eos_termination_counts={"natural_eos": 8, "forced_eos": 0, "token_limit": 0},
        scenario_labels=scenario_labels or ["speakers-quiet", "immediate-hard-stop"],
        release_gate_status="insufficient",
        listening_score=5,
        pressure_score=1,
    )


def _seed_evidence(store: LiveChatEvaluationStore, count: int = 5) -> list[str]:
    return [store.upsert(_create(f"call-{index}")).evaluation_id for index in range(count)]


def _policy_create(evidence_ids: list[str]) -> PresencePolicyVersionCreate:
    return PresencePolicyVersionCreate(
        values=PresencePolicyValues(
            silence_tolerance_ms=16_000,
            initiative_threshold_ms=20_000,
            initiative_cooldown_ms=50_000,
            listener_backchannel_frequency=0.14,
            typical_turn_words=65,
            interruption_sensitivity=0.74,
            response_onset_ms=450,
        ),
        reason="evidence-backed tuning trial",
        evidence_evaluation_ids=evidence_ids,
    )


def test_phase12_store_survives_restart_and_upserts_by_call(tmp_path: Path) -> None:
    path = tmp_path / "voice-evaluations.json"
    first = LiveChatEvaluationStore(path)
    created = first.upsert(_create())
    updated = first.upsert(_create().model_copy(update={"listening_score": 4}))

    assert created.evaluation_id == updated.evaluation_id
    assert updated.listening_score == 4
    assert len(first.list()) == 1

    restarted = LiveChatEvaluationStore(path)
    restored = restarted.get(created.evaluation_id)
    assert restored is not None
    assert restored.character_id == "maya"
    assert restored.browser_version == "Chrome 150.0.0"
    assert restored.resolved_duplex_mode == "echo_aware"
    assert restored.listening_score == 4


def test_phase12_schema_rejects_content_bearing_fields_and_metric_keys() -> None:
    with pytest.raises(ValidationError):
        VoiceSessionEvaluationCreate.model_validate({
            **_create().model_dump(mode="json"),
            "transcript": "private conversation",
        })
    with pytest.raises(ValidationError):
        VoiceSessionEvaluationCreate.model_validate({
            **_create().model_dump(mode="json"),
            "quality_metrics": {"transcript_excerpt": 1},
        })
    with pytest.raises(ValidationError):
        VoiceSessionEvaluationCreate.model_validate({
            **_create().model_dump(mode="json"),
            "scenario_labels": ["the user said private words"],
        })


def test_phase12_export_is_content_free(tmp_path: Path) -> None:
    store = LiveChatEvaluationStore(tmp_path / "voice-evaluations.json")
    store.upsert(_create())
    serialized = json.dumps(store.export(), sort_keys=True).casefold()

    assert "call-one" in serialized
    assert "transcript" not in serialized
    assert "raw_audio" not in serialized
    assert "message_content" not in serialized
    assert "prompt" not in serialized


def test_phase12_presence_policy_versions_are_evidence_validated_and_rollbackable(tmp_path: Path) -> None:
    store = LiveChatEvaluationStore(tmp_path / "voice-evaluations.json")
    original = store.active_policies()["natural"]
    evidence_ids = _seed_evidence(store)
    created = store.create_policy_version("natural", _policy_create(evidence_ids))

    assert created.version == original.version + 1
    assert created.active is False
    active = store.activate_policy("natural", created.version)
    assert active.active is True
    assert store.active_policies()["natural"].version == created.version
    rolled_back = store.rollback_policy("natural")
    assert rolled_back.version == original.version
    assert store.active_policies()["natural"].version == original.version


def test_phase12_policy_rejects_missing_or_mismatched_evidence(tmp_path: Path) -> None:
    store = LiveChatEvaluationStore(tmp_path / "voice-evaluations.json")
    evidence_ids = _seed_evidence(store, count=4)
    with pytest.raises(ValueError, match="at least 5"):
        store.create_policy_version("natural", _policy_create(evidence_ids))

    evidence_ids.append(
        store.upsert(_create("call-quiet").model_copy(update={"presence_preset": "quiet"})).evaluation_id
    )
    with pytest.raises(ValueError, match="match the selected preset"):
        store.create_policy_version("natural", _policy_create(evidence_ids))


def test_phase12_hidden_routes_persist_list_export_gate_and_manage_policies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "voice-evaluations.json"
    monkeypatch.setenv("OMNIX_LIVE_CHAT_EVALUATION_PATH", str(path))
    app = create_gateway_app(job_store_factory=lambda: EmptyJobStore())
    client = TestClient(app)

    evaluation_ids: list[str] = []
    for index in range(5):
        created = client.post(
            "/api/tts/live-call/evaluations",
            json=_create(
                f"call-{index}",
                character_id="system-assistant" if index == 0 else "maya",
            ).model_dump(mode="json"),
        )
        assert created.status_code == 200
        evaluation_ids.append(created.json()["evaluation_id"])

    listed = client.get("/api/tts/live-call/evaluations?session_id=chat%3Amaya")
    assert listed.status_code == 200
    assert len(listed.json()) == 5

    gate = client.get("/api/tts/live-call/evaluations/release-gate")
    assert gate.status_code == 200
    assert gate.json()["status"] == "insufficient"
    assert gate.json()["character_modes"] == ["character", "system"]
    assert gate.json()["metadata_records"]

    exported = client.get("/api/tts/live-call/evaluations/export")
    assert exported.status_code == 200
    assert exported.json()["evaluations"][0]["browser_version"] == "Chrome 150.0.0"

    policies = client.get("/api/tts/live-call/presence-presets")
    assert policies.status_code == 200
    assert set(policies.json()) == {"quiet", "natural", "engaged", "listener"}

    new_version = client.post(
        "/api/tts/live-call/presence-presets/natural/versions",
        json={
            "values": _policy_create(evaluation_ids).values.model_dump(mode="json"),
            "reason": "operator approved evidence tune",
            "evidence_evaluation_ids": evaluation_ids,
        },
    )
    assert new_version.status_code == 200
    version = new_version.json()["version"]
    activated = client.post(f"/api/tts/live-call/presence-presets/natural/activate/{version}")
    assert activated.status_code == 200
    assert activated.json()["active"] is True
    rolled_back = client.post("/api/tts/live-call/presence-presets/natural/rollback")
    assert rolled_back.status_code == 200
    assert rolled_back.json()["version"] == 1


def test_phase12_route_rejects_raw_conversation_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OMNIX_LIVE_CHAT_EVALUATION_PATH", str(tmp_path / "voice-evaluations.json"))
    client = TestClient(create_gateway_app(job_store_factory=lambda: EmptyJobStore()))
    response = client.post(
        "/api/tts/live-call/evaluations",
        json={**_create().model_dump(mode="json"), "prompt": "private system prompt"},
    )
    assert response.status_code == 422
