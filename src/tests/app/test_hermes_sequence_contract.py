from __future__ import annotations

from app.assist_core.hermes_sequence_contract import (
    hermes_sequence_contract,
    hermes_sequence_contract_validate,
)


def test_hermes_sequence_contract_normalizes_valid_multi_item_payload() -> None:
    result = hermes_sequence_contract_validate(
        {
            "sequence_id": "seq-1",
            "objective": "Scout the tavern safely",
            "domain": "rpg",
            "state_owner": "rpg_sim",
            "risk": "low",
            "items": [
                {
                    "item_id": "look",
                    "statement": "look around",
                    "guards": ["session exists"],
                    "expected_effect": "location details are refreshed",
                    "user_gate": True,
                },
                {
                    "statement": "ask the guard about rumors",
                    "expected_effect": "guard context is updated",
                },
            ],
        }
    )

    assert result["ok"] is True
    sequence = result["sequence"]
    assert sequence["sequence_id"] == "seq-1"
    assert sequence["objective"] == "Scout the tavern safely"
    assert sequence["domain"] == "rpg"
    assert sequence["state_owner"] == "rpg_sim"
    assert sequence["user_gate"] is True
    assert sequence["items"][0]["item_id"] == "look"
    assert sequence["items"][0]["guards"] == ["session exists"]
    assert sequence["items"][1]["item_id"] == "item-2"
    assert sequence["items"][1]["user_gate"] is True


def test_hermes_sequence_contract_reports_validation_errors() -> None:
    result = hermes_sequence_contract_validate(
        {
            "domain": "settings",
            "state_owner": "hermes",
            "items": [{"statement": ""}],
        }
    )

    assert result["ok"] is False
    assert result["errors"] == [
        "missing_objective",
        "unsupported_domain",
        "invalid_state_owner",
        "item_1_missing_statement",
    ]


def test_hermes_sequence_contract_defaults_empty_payload() -> None:
    sequence = hermes_sequence_contract({})

    assert sequence["sequence_id"] == "hermes-sequence-draft"
    assert sequence["domain"] == "rpg"
    assert sequence["state_owner"] == "rpg_sim"
    assert sequence["risk"] == "medium"
    assert sequence["status"] == "draft"
    assert sequence["items"] == []
