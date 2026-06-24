from __future__ import annotations

from app.rpg.narration_prompt_runtime import build_narration_prompt_runtime_metadata


def test_phase18_runtime_adapter_smoke() -> None:
    payload = build_narration_prompt_runtime_metadata(
        {"narration": "You count one ration.", "simulation_state": {"world": {}, "player": {}}},
        player_action="inventory",
    )

    assert payload["ready"] is True
    assert payload["prompt_profiles"]
