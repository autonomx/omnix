from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.companion_activity.initiative import (
    CompanionInitiativeAuthority,
    InitiativeAcquireRequest,
)
from app.companion_activity.presence import (
    CompanionPresenceInput,
    CompanionPresencePolicy,
)

NOW = datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc)


def request(
    *,
    session_id: str = "chat:1",
    generation: str = "generation:1",
    owner: str = "desktop",
    intent_id: str = "intent:1",
    channel: str = "text",
    urgency: str = "normal",
    interruptibility: str = "idle_only",
    requested_at: datetime = NOW,
    ttl_seconds: float = 15.0,
    minimum_spacing_seconds: float = 25.0,
) -> InitiativeAcquireRequest:
    return InitiativeAcquireRequest(
        session_id=session_id,
        generation=generation,
        owner=owner,
        intent_id=intent_id,
        channel=channel,
        urgency=urgency,
        interruptibility=interruptibility,
        requested_at=requested_at,
        ttl_seconds=ttl_seconds,
        minimum_spacing_seconds=minimum_spacing_seconds,
    )


def test_text_and_avatar_presence_do_not_require_voice_call() -> None:
    decision = CompanionPresencePolicy().decide(
        CompanionPresenceInput(
            mode="balanced",
            tab_visible=True,
            text_enabled=True,
            avatar_available=True,
            voice_call_connected=False,
            voice_output_enabled=False,
        )
    )

    assert decision.can_text is True
    assert decision.can_avatar is True
    assert decision.can_voice is False
    assert "voice_call_not_connected" in decision.reasons


def test_quiet_and_sensitive_presence_limit_externalized_channels() -> None:
    quiet = CompanionPresencePolicy().decide(
        CompanionPresenceInput(
            mode="quiet",
            text_enabled=True,
            avatar_available=True,
            voice_call_connected=True,
            voice_output_enabled=True,
        )
    )
    assert quiet.can_text is True
    assert quiet.can_avatar is True
    assert quiet.can_voice is False

    sensitive = CompanionPresencePolicy().decide(
        CompanionPresenceInput(
            mode="chatty",
            tab_visible=False,
            notifications_enabled=True,
            voice_call_connected=True,
            voice_output_enabled=True,
            sensitive_activity=True,
        )
    )
    assert sensitive.can_voice is False
    assert sensitive.can_notify is False
    assert "sensitive_activity_limits_externalized_channels" in sensitive.reasons


def test_initiative_authority_is_session_scoped() -> None:
    authority = CompanionInitiativeAuthority()

    first = authority.acquire(request(session_id="chat:1", intent_id="intent:a"))
    second = authority.acquire(request(session_id="chat:2", intent_id="intent:b"))

    assert first.accepted is True
    assert second.accepted is True
    assert first.lease is not None
    assert second.lease is not None
    assert first.lease.session_id != second.lease.session_id


def test_lost_finish_cannot_deadlock_session_because_lease_expires() -> None:
    authority = CompanionInitiativeAuthority()
    acquired = authority.acquire(request(ttl_seconds=2.0))
    assert acquired.accepted is True

    blocked = authority.acquire(
        request(intent_id="intent:blocked", requested_at=NOW + timedelta(seconds=1))
    )
    assert blocked.accepted is False
    assert blocked.reason == "initiative_active"

    recovered = authority.acquire(
        request(intent_id="intent:recovered", requested_at=NOW + timedelta(seconds=3))
    )
    assert recovered.accepted is True


def test_generation_change_invalidates_old_lease_and_stale_generation() -> None:
    authority = CompanionInitiativeAuthority()
    authority.register_generation("chat:1", "generation:1")
    acquired = authority.acquire(request())
    assert acquired.accepted is True

    snapshot = authority.register_generation("chat:1", "generation:2")
    assert snapshot.active_lease is None

    stale = authority.acquire(
        request(generation="generation:1", intent_id="intent:stale")
    )
    assert stale.accepted is False
    assert stale.reason == "stale_generation"


def test_spacing_and_repetition_debt_are_deterministic() -> None:
    authority = CompanionInitiativeAuthority()
    first = authority.acquire(request(owner="desktop", intent_id="intent:1"))
    assert first.lease is not None
    assert authority.finish(
        session_id="chat:1",
        lease_id=first.lease.lease_id,
        finished_at=NOW,
        delivered=True,
    )

    blocked = authority.acquire(
        request(
            owner="social",
            intent_id="intent:2",
            requested_at=NOW + timedelta(seconds=10),
        )
    )
    assert blocked.accepted is False
    assert blocked.reason == "initiative_spacing"

    second = authority.acquire(
        request(
            owner="desktop",
            intent_id="intent:3",
            requested_at=NOW + timedelta(seconds=30),
        )
    )
    assert second.accepted is True
    assert second.lease is not None
    assert authority.finish(
        session_id="chat:1",
        lease_id=second.lease.lease_id,
        finished_at=NOW + timedelta(seconds=30),
        delivered=True,
    )

    third = authority.acquire(
        request(
            owner="desktop",
            intent_id="intent:4",
            requested_at=NOW + timedelta(seconds=60),
        )
    )
    assert third.accepted is False
    assert third.reason == "initiative_spacing"
    assert third.eligible_in_ms >= 19_000


def test_critical_interrupt_can_preempt_weaker_lease() -> None:
    authority = CompanionInitiativeAuthority()
    normal = authority.acquire(request(intent_id="intent:normal"))
    assert normal.accepted is True

    critical = authority.acquire(
        request(
            owner="safety",
            intent_id="intent:critical",
            channel="voice",
            urgency="critical",
            interruptibility="interrupt",
            requested_at=NOW + timedelta(milliseconds=100),
        )
    )
    assert critical.accepted is True
    assert critical.reason == "preempted_by_critical_interrupt"
    assert critical.lease is not None
    assert critical.lease.intent_id == "intent:critical"
