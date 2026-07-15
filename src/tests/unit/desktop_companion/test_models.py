from __future__ import annotations

from datetime import timedelta

import pytest

from app.desktop_companion.models import (
    CompanionAttentionDecision,
    DesktopActivitySignal,
    DesktopBehaviorState,
    DesktopObservation,
    utcnow,
)


def test_observation_contract_accepts_versioned_bounded_state():
    captured_at = utcnow()
    observation = DesktopObservation(
        observation_id="obs-1",
        session_id="chat-1",
        character_id="character-1",
        capture_generation="capture-1",
        source_fingerprint="screen-1",
        client_sequence=4,
        captured_at=captured_at,
        expires_at=captured_at + timedelta(seconds=12),
        activity=DesktopActivitySignal(
            activity="localized_change",
            hypothesis="likely_typing",
            confidence=0.62,
            changed_ratio=0.08,
        ),
        behavior=DesktopBehaviorState(
            current_pattern="typing",
            likely_typing=True,
            sample_count=5,
        ),
    )

    assert observation.schema_version == 1
    assert observation.is_stale(captured_at + timedelta(seconds=11)) is False
    assert observation.is_stale(captured_at + timedelta(seconds=12)) is True


def test_observation_rejects_non_future_expiry():
    captured_at = utcnow()
    with pytest.raises(ValueError, match="expires_at"):
        DesktopObservation(
            observation_id="obs-1",
            session_id="chat-1",
            capture_generation="capture-1",
            source_fingerprint="screen-1",
            client_sequence=0,
            captured_at=captured_at,
            expires_at=captured_at,
        )


def test_attention_decision_rejects_unbounded_sentence_targets():
    with pytest.raises(ValueError):
        CompanionAttentionDecision(
            reaction="deep",
            should_generate=True,
            should_deliver=True,
            target_sentences=5,
            rationale="too long",
        )
