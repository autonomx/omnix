from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.companion_activity.channels import CompanionChannelCoordinator
from app.companion_activity.cognition import DeliveryIntent
from app.companion_activity.initiative import InitiativeLease
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


def lease(
    *,
    channel: str = "text",
    intent_id: str = "intent:1",
    session_id: str = "chat:1",
):
    return InitiativeLease(
        lease_id="lease:1",
        session_id=session_id,
        generation="generation:1",
        owner="companion",
        intent_id=intent_id,
        channel=channel,
        urgency="normal",
        interruptibility="idle_only",
        acquired_at=NOW,
        expires_at=NOW + timedelta(seconds=15),
    )


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
    plan = CompanionChannelCoordinator().coordinate(
        intent=intent("IGNORE"),
        lease=lease(),
        presence=presence(),
    )
    assert plan.actions == ()
    assert plan.suppressed_reason == "intent_ignore"


def test_delivery_requires_matching_initiative_lease() -> None:
    coordinator = CompanionChannelCoordinator()
    missing = coordinator.coordinate(intent=intent(), lease=None, presence=presence())
    assert missing.actions == ()
    assert missing.suppressed_reason == "initiative_lease_required"

    with pytest.raises(ValueError, match="does not authorize"):
        coordinator.coordinate(
            intent=intent(),
            lease=lease(intent_id="intent:other"),
            presence=presence(),
        )


def test_presence_can_suppress_the_authorized_primary_channel() -> None:
    plan = CompanionChannelCoordinator().coordinate(
        intent=intent(),
        lease=lease(channel="voice"),
        presence=presence(can_voice=False),
    )
    assert plan.actions == ()
    assert plan.suppressed_reason == "presence_disallows_voice"


def test_text_delivery_can_include_nonverbal_avatar_adjunct() -> None:
    plan = CompanionChannelCoordinator().coordinate(
        intent=intent("CELEBRATE"),
        lease=lease(channel="text"),
        presence=presence(can_text=True, can_avatar=True),
    )
    assert [item.channel for item in plan.actions] == ["text", "avatar"]
    assert plan.actions[0].primary is True
    assert plan.actions[1].primary is False
    assert all(item.semantic_action == "CELEBRATE" for item in plan.actions)


def test_voice_delivery_does_not_implicitly_require_text() -> None:
    plan = CompanionChannelCoordinator().coordinate(
        intent=intent("WARN"),
        lease=lease(channel="voice"),
        presence=presence(can_text=False, can_avatar=False, can_voice=True),
    )
    assert len(plan.actions) == 1
    assert plan.actions[0].channel == "voice"
    assert plan.actions[0].semantic_action == "WARN"
