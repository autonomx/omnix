from __future__ import annotations

from app.desktop_companion.models import DesktopActivitySignal, DesktopBehaviorState, DesktopCompanionPolicy
from app.desktop_companion.shadow_watch import decide_shadow_watch


def activity(**updates):
    values = {
        "activity": "localized_change",
        "hypothesis": "likely_navigation",
        "confidence": 0.8,
        "changed_ratio": 0.4,
        "mean_difference": 0.2,
    }
    values.update(updates)
    return DesktopActivitySignal(**values)


def behavior(**updates):
    values = {"current_pattern": "mixed", "sample_count": 4}
    values.update(updates)
    return DesktopBehaviorState(**values)


def decision(**updates):
    values = {
        "policy": DesktopCompanionPolicy(enabled=True),
        "activity": activity(),
        "behavior": behavior(),
        "watch_enabled": True,
        "page_visible": True,
        "provider_ready": True,
        "request_active": False,
        "pending_request": False,
        "now_ms": 20_000,
        "last_observation_started_ms": 10_000,
        "coordinator_eligible_in_ms": 0,
    }
    values.update(updates)
    return decide_shadow_watch(**values)


def test_shadow_watch_submits_only_meaningful_eligible_changes():
    result = decision()
    assert result.action == "submit"
    assert result.reason == "meaningful_change_available"


def test_shadow_watch_suppresses_static_and_low_confidence_changes():
    assert decision(activity=activity(activity="static", confidence=0.95)).reason == "no_meaningful_visual_change"
    assert decision(activity=activity(confidence=0.3)).reason == "change_confidence_below_threshold"


def test_shadow_watch_waits_for_repeated_typing_and_rapid_browsing():
    typing = decision(behavior=behavior(current_pattern="typing", likely_typing=True, sample_count=4))
    browsing = decision(behavior=behavior(current_pattern="browsing", rapid_browsing=True))
    assert typing.action == "wait"
    assert typing.reason == "likely_typing"
    assert browsing.action == "wait"
    assert browsing.reason == "rapid_browsing"


def test_shadow_watch_enforces_interval_and_provider_state():
    interval = decision(now_ms=12_000)
    unavailable = decision(provider_ready=False)
    assert interval.action == "wait"
    assert interval.eligible_in_ms == 6_000
    assert unavailable.action == "suppress"
    assert unavailable.reason == "vision_provider_unavailable"
