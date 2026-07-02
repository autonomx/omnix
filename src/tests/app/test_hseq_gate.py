from __future__ import annotations

from app.assist_core.hermes_sequence_gate import hermes_sequence_apply_gate, hermes_sequence_gate_decision


def test_gate_allows_plain_item() -> None:
    result = hermes_sequence_gate_decision(
        {"sequence_id": "seq-1", "state_owner": "rpg_sim", "risk": "low"},
        {"item_id": "look", "statement": "look around", "user_gate": False},
    )

    assert result["allowed"] is True
    assert result["reason"] is None


def test_gate_flags_marked_item() -> None:
    result = hermes_sequence_gate_decision(
        {"sequence_id": "seq-1", "state_owner": "rpg_sim", "risk": "low"},
        {"item_id": "local", "statement": "local update", "user_gate": True},
    )

    assert result["allowed"] is False
    assert result["reason"] == "item_requires_review"


def test_gate_summary_counts_items() -> None:
    result = hermes_sequence_apply_gate(
        {
            "sequence_id": "seq-1",
            "state_owner": "rpg_sim",
            "risk": "low",
            "items": [
                {"item_id": "look", "statement": "look around", "user_gate": False},
                {"item_id": "local", "statement": "local update", "user_gate": True},
            ],
        }
    )

    assert result["allowed"] is False
    assert len(result["decisions"]) == 2
