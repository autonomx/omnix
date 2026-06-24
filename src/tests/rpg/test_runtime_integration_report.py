from __future__ import annotations

import json

from app.rpg.runtime_integration_report import (
    RUNTIME_INTEGRATION_SOURCE,
    attach_runtime_integration_to_autoplay_summary,
    attach_runtime_integration_to_row,
    build_turn_runtime_integration_report,
)


def _state() -> dict[str, object]:
    return {
        "world": {"region": "vance"},
        "player": {"name": "Scout"},
        "party": {},
        "npcs": {},
        "quests": {},
        "map": {},
        "inventory": {"items": ["ration"]},
        "combat": {},
        "memory": {},
        "seed": 42,
        "counters": {"rng": 1},
        "director_state": {
            "arcs": [{"arc_id": "bandits", "title": "Bandit Trail", "threat": "follow tracks"}],
            "recent_actions": ["look"],
        },
    }


def test_runtime_integration_report_is_report_facing_payload() -> None:
    report = build_turn_runtime_integration_report(
        {
            "narration": "You check your pack and confirm the ration is still there.",
            "simulation_state": _state(),
            "action_kind": "inventory",
            "valid_actions": ["inventory", "check journal"],
        },
        turn_index=1,
        player_action="inventory",
    )

    assert report["source"] == RUNTIME_INTEGRATION_SOURCE
    assert report["ready"] is True
    assert report["issues"] == []
    assert report["phase16_report"]["fast_action"]["requires_heavy_llm"] is False
    assert set(report["state_groups_present"]) >= {"world", "player", "inventory", "memory"}


def test_attach_runtime_integration_to_row_uses_recent_narration_context() -> None:
    previous = [{"turn_index": 1, "narration": "The rain taps the old roof."}]
    row = attach_runtime_integration_to_row(
        {
            "turn_index": 2,
            "player_action": "look",
            "narration": "The rain taps the old roof.",
            "turn_result": {
                "narration": "The rain taps the old roof.",
                "simulation_state": _state(),
                "action_kind": "look",
            },
        },
        previous_rows=previous,
    )

    payload = row["runtime_integration_report"]
    assert payload["source"] == RUNTIME_INTEGRATION_SOURCE
    assert "narration_rewrite_required" in payload["issues"]
    assert payload["phase16_report"]["rewrite_contract"]["rewrite_requested"] is True


def test_autoplay_summary_integration_persists_json_artifacts(tmp_path) -> None:
    summary_path = tmp_path / "summary.json"
    transcript_path = tmp_path / "autoplay-transcript.json"
    summary = {
        "transcript_rows": [
            {
                "turn_index": 1,
                "player_action": "inventory",
                "narration": "You check your pack and confirm the ration is still there.",
                "turn_result": {
                    "narration": "You check your pack and confirm the ration is still there.",
                    "simulation_state": _state(),
                    "action_kind": "inventory",
                    "valid_actions": ["inventory"],
                },
            }
        ],
        "artifact_paths": {"summary": str(summary_path), "transcript": str(transcript_path)},
    }

    result = attach_runtime_integration_to_autoplay_summary(summary, persist=True)

    assert result["runtime_integration"]["turn_count"] == 1
    assert result["runtime_integration"]["ready_turn_count"] == 1
    persisted = json.loads(summary_path.read_text(encoding="utf-8"))
    assert persisted["runtime_integration"]["source"] == RUNTIME_INTEGRATION_SOURCE
    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    assert transcript[0]["runtime_integration_report"]["ready"] is True
