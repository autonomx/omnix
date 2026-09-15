from __future__ import annotations

from datetime import datetime, timezone

from app.companion_activity.authority import authority_source_for
from app.companion_activity.integrations import CompanionIntegrationEvidenceAdapter

NOW = datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)


def test_runtime_and_process_integrations_produce_trusted_evidence_only() -> None:
    adapter = CompanionIntegrationEvidenceAdapter()
    runtime = adapter.runtime_fact(
        source_id="live-voice",
        event_id="voice:connected:1",
        subject="activity:1",
        predicate="voice_call_connected",
        value=True,
        observed_at=NOW,
        generation="generation:1",
    )
    process = adapter.process_fact(
        source_id="os-window",
        event_id="window:1",
        subject="activity:1",
        predicate="foreground_application",
        value="eldenring.exe",
        observed_at=NOW,
    )

    assert runtime.source_kind == "runtime"
    assert runtime.trust_level == "system_trusted"
    assert authority_source_for(runtime) == "runtime_state"
    assert process.source_kind == "system"
    assert process.trust_level == "system_trusted"
    assert authority_source_for(process) == "trusted_process_integration"


def test_game_telemetry_has_deterministic_telemetry_authority() -> None:
    proposition = CompanionIntegrationEvidenceAdapter().telemetry(
        source_id="elden-ring-plugin",
        event_id="attempt:7",
        subject="activity:1",
        predicate="attempt_count",
        value=7,
        observed_at=NOW,
    )

    assert proposition.source_kind == "telemetry"
    assert proposition.trust_level == "system_trusted"
    assert authority_source_for(proposition) == "deterministic_telemetry"


def test_browser_metadata_remains_untrusted_and_sensitive() -> None:
    proposition = CompanionIntegrationEvidenceAdapter().browser_metadata(
        source_id="browser-tab",
        event_id="tab:42",
        subject="activity:1",
        predicate="browser_title",
        value="Private account statement",
        observed_at=NOW,
    )

    assert proposition.source_kind == "external"
    assert proposition.trust_level == "external_untrusted"
    assert proposition.sensitivity == "sensitive"
    assert authority_source_for(proposition) == "single_perception"


def test_explicit_user_correction_stays_independent_from_machine_evidence() -> None:
    proposition = CompanionIntegrationEvidenceAdapter().user_explicit(
        source_id="chat-user",
        event_id="turn:882",
        subject="activity:1",
        predicate="current_objective",
        value="farm runes",
        observed_at=NOW,
    )

    assert proposition.source_kind == "user"
    assert proposition.trust_level == "user_explicit"
    assert authority_source_for(proposition) == "user_explicit"
    assert proposition.links == ()


def test_integration_event_identity_is_stable_for_replay_inputs() -> None:
    adapter = CompanionIntegrationEvidenceAdapter()
    first = adapter.telemetry(
        source_id="game-plugin",
        event_id="event:99",
        subject="activity:1",
        predicate="current_phase",
        value="phase_two",
        observed_at=NOW,
    )
    second = adapter.telemetry(
        source_id="game-plugin",
        event_id="event:99",
        subject="activity:1",
        predicate="current_phase",
        value="phase_two",
        observed_at=NOW,
    )
    assert first.proposition_id == second.proposition_id
