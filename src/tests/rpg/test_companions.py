from __future__ import annotations

from app.rpg.companions import (
    CompanionState,
    companion_can_join,
    companion_report_payload,
    join_companion,
    leave_companion,
    party_bonus,
    party_from_companions,
)


def test_companion_can_join_requires_relationship_and_no_conflict() -> None:
    bran = CompanionState("bran", "fighter", loyalty=5)

    assert companion_can_join(bran, relationship_ok=True) is True
    assert companion_can_join(bran, relationship_ok=False) is False
    assert companion_can_join(bran, relationship_ok=True, conflict=True) is False


def test_join_companion_updates_party_purely() -> None:
    bran = CompanionState("bran", "fighter", loyalty=5)
    party = party_from_companions([bran])
    result = join_companion(party, bran, relationship_ok=True)

    assert result.decision == "joined"
    assert not party.companions["bran"].in_party
    assert result.party.companions["bran"].in_party


def test_leave_companion_marks_member_inactive() -> None:
    bran = CompanionState("bran", "fighter", in_party=True)
    party = party_from_companions([bran])
    result = leave_companion(party, "bran", reason="low_morale")

    assert result.decision == "left"
    assert result.party.companions["bran"].in_party is False


def test_companion_deltas_are_clamped() -> None:
    bran = CompanionState("bran", "fighter", loyalty=95).with_delta(loyalty=50, fear=-200)

    assert bran.loyalty == 100
    assert bran.fear == -100


def test_party_bonus_uses_active_roles() -> None:
    party = party_from_companions(
        [CompanionState("bran", "fighter", in_party=True), CompanionState("elara", "merchant", in_party=True)]
    )

    assert party_bonus(party, "combat") == 2
    assert party_bonus(party, "social") == 2
    assert party_bonus(party, "locks") == 0


def test_companion_report_payload_only_lists_active_members() -> None:
    party = party_from_companions([CompanionState("bran", "fighter", in_party=True), CompanionState("elara", "merchant")])
    payload = companion_report_payload(party)

    assert payload["party_size"] == 1
    assert payload["companions"][0]["npc_id"] == "bran"
