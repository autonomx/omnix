from __future__ import annotations

from datetime import timedelta

from app.desktop_companion.attention import DesktopAttentionContext, decide_desktop_attention
from app.desktop_companion.models import (
    DesktopActivitySignal,
    DesktopBehaviorState,
    DesktopCompanionPolicy,
    DesktopObservation,
    DesktopObservedChange,
    DesktopObservedValue,
    utcnow,
)


def observation(
    *,
    activity: str = "localized_change",
    hypothesis: str = "likely_navigation",
    behavior_pattern: str = "mixed",
    rapid_browsing: bool = False,
    likely_typing: bool = False,
    change_kind: str = "scene_change",
    importance: float = 0.9,
    confidence: float = 0.9,
) -> DesktopObservation:
    now = utcnow()
    return DesktopObservation(
        observation_id="obs-attention",
        session_id="chat-1",
        capture_generation="capture-1",
        source_fingerprint="screen-1",
        client_sequence=1,
        captured_at=now,
        observed_at=now,
        expires_at=now + timedelta(seconds=12),
        activity=DesktopActivitySignal(
            activity=activity,
            hypothesis=hypothesis,
            confidence=confidence,
            changed_ratio=0.5,
            mean_difference=0.3,
        ),
        behavior=DesktopBehaviorState(
            current_pattern=behavior_pattern,
            rapid_browsing=rapid_browsing,
            likely_typing=likely_typing,
            sample_count=5,
        ),
        change_kind=change_kind,
        current_scene=DesktopObservedValue(value="A new game area", confidence=confidence),
        visible_changes=[
            DesktopObservedChange(
                event="The scene changed",
                confidence=confidence,
                fingerprint="change:scene",
            )
        ],
        importance=importance,
    )


def active_policy(**updates) -> DesktopCompanionPolicy:
    values = {"enabled": True, "shadow_mode": False, "speech_enabled": True}
    values.update(updates)
    return DesktopCompanionPolicy(**values)


def test_high_confidence_important_scene_change_receives_deep_attention():
    result = decide_desktop_attention(
        observation(),
        policy=active_policy(),
        context=DesktopAttentionContext(scene_age_seconds=2),
    )

    assert result.reaction == "deep"
    assert result.should_generate is True
    assert result.should_deliver is True
    assert result.target_sentences == 3
    assert "scene_change" in result.rationale
    assert "high_importance" in result.rationale


def test_repeated_typing_and_rapid_browsing_choose_restraint():
    typing = decide_desktop_attention(
        observation(
            activity="localized_change",
            hypothesis="likely_typing",
            behavior_pattern="typing",
            likely_typing=True,
            importance=0.4,
            confidence=0.65,
            change_kind="delta",
        ),
        policy=active_policy(),
    )
    browsing = decide_desktop_attention(
        observation(
            behavior_pattern="browsing",
            rapid_browsing=True,
            importance=0.4,
            confidence=0.65,
            change_kind="delta",
        ),
        policy=active_policy(),
    )

    assert typing.reaction in {"ignore", "observe_silently"}
    assert typing.should_generate is False
    assert browsing.reaction in {"ignore", "observe_silently"}
    assert browsing.should_generate is False


def test_cooldown_and_reaction_streak_increase_silence_pressure():
    result = decide_desktop_attention(
        observation(importance=0.55, confidence=0.7, change_kind="delta"),
        policy=active_policy(commentary_cooldown_ms=25_000),
        context=DesktopAttentionContext(
            seconds_since_comment=2,
            visual_reaction_streak=4,
        ),
    )

    assert result.reaction in {"ignore", "observe_silently"}
    assert "commentary_cooldown" in result.rationale
    assert "reaction_streak" in result.rationale


def test_busy_conversation_floor_blocks_generation_and_delivery():
    result = decide_desktop_attention(
        observation(),
        policy=active_policy(),
        context=DesktopAttentionContext(user_floor_active=True),
    )

    assert result.reaction == "observe_silently"
    assert result.should_generate is False
    assert result.should_deliver is False
    assert "conversation_floor_busy" in result.rationale


def test_shadow_mode_records_decision_without_generating_commentary():
    result = decide_desktop_attention(
        observation(),
        policy=DesktopCompanionPolicy(enabled=True, shadow_mode=True),
    )

    assert result.reaction == "deep"
    assert result.should_generate is False
    assert result.should_deliver is False
    assert "shadow_mode" in result.rationale


def test_organic_selection_is_replayable_for_same_observation_and_seed():
    policy = active_policy(attention_seed=42)
    context = DesktopAttentionContext(selection_mode="organic")
    first = decide_desktop_attention(observation(), policy=policy, context=context)
    second = decide_desktop_attention(observation(), policy=policy, context=context)

    assert first.reaction == second.reaction
    assert first.scores == second.scores
