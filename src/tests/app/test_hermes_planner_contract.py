from __future__ import annotations

from app.assist_core.hermes_planner_contract import (
    hermes_planner_contract_schema,
    normalize_hermes_planner_response,
)


def test_hermes_planner_contract_schema_marks_command_only_response() -> None:
    schema = hermes_planner_contract_schema()

    assert schema["response"]["command"] == "single RPG command string"
    assert schema["response"]["direct_state_write"] is False
    assert schema["request"]["context"] == "bounded visible RPG context"


def test_hermes_planner_contract_accepts_single_known_command() -> None:
    payload = normalize_hermes_planner_response(
        {
            "command": "ask Bran about the witness",
            "reason": "Bran is present.",
            "confidence": 0.8,
            "risk": "low",
            "expected_effect": "new dialogue clue",
            "planner": "test",
            "kind": "dialogue",
        }
    )

    assert payload["ok"] is True
    assert payload["proposal"]["command"] == "ask Bran about the witness"
    assert payload["proposal"]["confidence"] == 0.8
    assert payload["proposal"]["requires_review"] is True
    assert payload["proposal"]["direct_state_write"] is False
    assert payload["metadata"] == {"planner": "test", "raw_kind": "dialogue"}


def test_hermes_planner_contract_normalizes_alias_prefixes() -> None:
    payload = normalize_hermes_planner_response({"command": "purchase two rations"})

    assert payload["ok"] is True
    assert payload["proposal"]["command"] == "buy two rations"


def test_hermes_planner_contract_rejects_empty_command() -> None:
    assert normalize_hermes_planner_response({"command": "   "})["error"] == "empty_command"


def test_hermes_planner_contract_rejects_state_patch() -> None:
    payload = normalize_hermes_planner_response(
        {"command": "check inventory", "state_patch": {"gold": 99}}
    )

    assert payload["ok"] is False
    assert payload["error"] == "state_mutation_not_allowed"
    assert payload["mutation_keys"] == ["state_patch"]


def test_hermes_planner_contract_rejects_unknown_command() -> None:
    payload = normalize_hermes_planner_response({"command": "teleport to the vault"})

    assert payload["ok"] is False
    assert payload["error"] == "unknown_command"


def test_hermes_planner_contract_rejects_multi_command_bundle() -> None:
    payload = normalize_hermes_planner_response({"command": "check inventory then buy rations"})

    assert payload["ok"] is False
    assert payload["error"] == "multi_command_not_allowed"
