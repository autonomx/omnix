from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.companion_activity.channels import CompanionChannelCoordinator
from app.companion_activity.cognition import DeliveryIntent
from app.companion_activity.initiative import (
    CompanionInitiativeAuthority,
    InitiativeAcquireRequest,
    InitiativeLease,
)
from app.companion_activity.presence import CompanionPresenceDecision

NOW = datetime(2026, 9, 15, 7, 0, tzinfo=timezone.utc)


def intent(kind: str = "REACT", *, intent_id: str = "intent:1", session_id: str = "chat:1"):
    return DeliveryIntent(
        intent_id=intent_id,
        session_id=session_id,
        kind=kind,
        reason="test intent",
        grounding_proposition_ids=("p:1",),
        confidence=0.9,
        salience=0.8,
        created_at=NOW,
    )


def acquire(
    authority: CompanionInitiativeAuthority,
    *,
    channel: str = "text",
    intent_id: str = "intent:1",
    session_id: str = "chat:1",
    owner: str = "companion",
    urgency: str = "normal",
    interruptibility: str = "idle_only",
    requested_at: datetime = NOW,
    ttl_seconds: float = 15.0,
) -> InitiativeLease:
    decision = authority.acquire(
        InitiativeAcquireRequest(
            session_id=session_id,
            generation="generation:1",
            owner=owner,
            intent_id=intent_id,
            channel=channel,
            urgency=urgency,
            interruptibility=interruptibility,
            requested_at=requested_at,
            ttl_seconds=ttl_seconds,
            minimum_spacing_seconds=0,
        )
    )
    assert decision.accepted is True
    assert decision.lease is not None
    return decision.lease


def presence(**updates):
    values = {
        "can_text": True,
        "can_avatar": True,
        "can_voice": False,
        "can_notify": False,
        "reasons": (),
    }
    values.update(updates)
    return CompanionPresenceDecision(**values)


def test_ignore_never_produces_channel_actions() -> None:
    authority = CompanionInitiativeAuthority()
    plan = CompanionChannelCoordinator(authority).coordinate(
        intent=intent("IGNORE"),
        lease=None,
        presence=presence(),
        now=NOW,
    )
    assert plan.actions == ()
    assert plan.suppressed_reason == "intent_ignore"


def test_delivery_requires_matching_initiative_lease() -> None:
    authority = CompanionInitiativeAuthority()
    coordinator = CompanionChannelCoordinator(authority)
    missing = coordinator.coordinate(
        intent=intent(),
        lease=None,
        presence=presence(),
        now=NOW,
    )
    assert missing.actions == ()
    assert missing.suppressed_reason == "initiative_lease_required"

    wrong = acquire(authority, intent_id="intent:other")
    with pytest.raises(ValueError, match="does not authorize"):
        coordinator.coordinate(
            intent=intent(),
            lease=wrong,
            presence=presence(),
            now=NOW,
        )


def test_presence_can_suppress_the_authorized_primary_channel() -> None:
    authority = CompanionInitiativeAuthority()
    active = acquire(authority, channel="voice")
    plan = CompanionChannelCoordinator(authority).coordinate(
        intent=intent(),
        lease=active,
        presence=presence(can_voice=False),
        now=NOW,
    )
    assert plan.actions == ()
    assert plan.suppressed_reason == "presence_disallows_voice"


def test_text_delivery_can_include_nonverbal_avatar_adjunct() -> None:
    authority = CompanionInitiativeAuthority()
    active = acquire(authority, channel="text")
    plan = CompanionChannelCoordinator(authority).coordinate(
        intent=intent("CELEBRATE"),
        lease=active,
        presence=presence(can_text=True, can_avatar=True),
        now=NOW,
    )
    assert [item.channel for item in plan.actions] == ["text", "avatar"]
    assert plan.actions[0].primary is True
    assert plan.actions[1].primary is False
    assert all(item.semantic_action == "CELEBRATE" for item in plan.actions)


def test_voice_delivery_does_not_implicitly_require_text() -> None:
    authority = CompanionInitiativeAuthority()
    active = acquire(authority, channel="voice")
    plan = CompanionChannelCoordinator(authority).coordinate(
        intent=intent("WARN"),
        lease=active,
        presence=presence(can_text=False, can_avatar=False, can_voice=True),
        now=NOW,
    )
    assert len(plan.actions) == 1
    assert plan.actions[0].channel == "voice"
    assert plan.actions[0].semantic_action == "WARN"


def test_expired_lease_cannot_be_replayed_as_authority() -> None:
    authority = CompanionInitiativeAuthority()
    active = acquire(authority, ttl_seconds=1.0)

    plan = CompanionChannelCoordinator(authority).coordinate(
        intent=intent(),
        lease=active,
        presence=presence(),
        now=NOW + timedelta(seconds=2),
    )

    assert plan.actions == ()
    assert plan.suppressed_reason == "initiative_lease_inactive"


def test_preempted_lease_cannot_render_after_critical_takeover() -> None:
    authority = CompanionInitiativeAuthority()
    old = acquire(authority, intent_id="intent:old")
    replacement = acquire(
        authority,
        channel="voice",
        intent_id="intent:critical",
        owner="safety",
        urgency="critical",
        interruptibility="interrupt",
        requested_at=NOW + timedelta(milliseconds=100),
    )

    stale_plan = CompanionChannelCoordinator(authority).coordinate(
        intent=intent(intent_id="intent:old"),
        lease=old,
        presence=presence(),
        now=NOW + timedelta(milliseconds=200),
    )
    current_plan = CompanionChannelCoordinator(authority).coordinate(
        intent=intent("WARN", intent_id="intent:critical"),
        lease=replacement,
        presence=presence(can_voice=True),
        now=NOW + timedelta(milliseconds=200),
    )

    assert stale_plan.actions == ()
    assert stale_plan.suppressed_reason == "initiative_lease_inactive"
    assert current_plan.actions[0].channel == "voice"
