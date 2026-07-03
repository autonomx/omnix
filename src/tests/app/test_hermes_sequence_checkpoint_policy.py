from __future__ import annotations

from app.assist_core.hermes_sequence_checkpoint_policy import (
    hermes_sequence_checkpoint_policy,
    hermes_sequence_checkpoint_reason,
)


def base_sequence(statement: str, **overrides: object) -> dict:
    return {
        "sequence_id": "seq-1",
        "state_owner": overrides.pop("state_owner", "rpg_sim"),
        "risk": overrides.pop("risk", "low"),
        "items": [{"item_id": "item-1", "statement": statement}],
        **overrides,
    }


def test_checkpoint_policy_flags_risky_stateful_steps() -> None:
    cases = {
        "buy rope": "inventory_currency_change",
        "travel north": "travel_location_change",
        "attack the bandit": "combat_action",
        "complete the quest": "quest_state_change",
        "recruit Bran": "npc_relationship_change",
        "wait again": "repeated_noop_command",
    }

    for statement, reason in cases.items():
        assert hermes_sequence_checkpoint_reason(base_sequence(statement), {"statement": statement}) == reason


def test_checkpoint_policy_flags_invalid_owner_and_high_risk() -> None:
    assert hermes_sequence_checkpoint_policy(base_sequence("look around", state_owner="external"))["reason"] == "invalid_state_owner"
    assert hermes_sequence_checkpoint_policy(base_sequence("look around", risk="high"))["reason"] == "high_risk_sequence"


def test_checkpoint_policy_allows_low_risk_observation() -> None:
    result = hermes_sequence_checkpoint_policy(base_sequence("look around"))

    assert result["requires_checkpoint"] is False
    assert result["reason"] is None
    assert result["decisions"][0]["requires_checkpoint"] is False
