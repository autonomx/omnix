from app.rpg.session.environment_narration import (
    build_environment_narration_contract,
    environment_narration_prompt_block,
)


def _snapshot() -> dict[str, object]:
    return {
        "weather": {"condition": "rain", "intensity": "moderate"},
        "display": {"day_time": "Day 1 • 08:00", "weather": "Moderate Rain", "temperature": "9°C", "terrain": "Muddy"},
    }


def test_environment_narration_contract_is_read_only() -> None:
    contract = build_environment_narration_contract(_snapshot())

    assert contract["authority"] == "read_only_environment_snapshot"
    assert contract["environment_snapshot"]["weather"]["condition"] == "rain"
    assert "create_new_weather" in contract["forbidden"]
    assert "advance_time" in contract["forbidden"]
    assert "describe_current_snapshot" in contract["allowed"]


def test_environment_prompt_block_contains_snapshot_and_mutation_rule() -> None:
    prompt = environment_narration_prompt_block(_snapshot())

    assert "Environment Snapshot (read-only)" in prompt
    assert "Moderate Rain" in prompt
    assert "Day 1 • 08:00" in prompt
    assert "never mutate weather" in prompt
