from __future__ import annotations

from tests.rpg.autoplay.wizard_new_game_validation import build_wizard_new_game_validation


def _new_game_prepared() -> dict[str, object]:
    return {
        "session_id": "rpg_test",
        "session": {
            "manifest": {"session_id": "rpg_test", "kind": "new_game"},
            "runtime_state": {"created_from": "new_game"},
            "setup_payload": {
                "campaign_template": "classic_fantasy",
                "difficulty": "harsh",
                "world_activity": "living_world",
                "economy_pressure": "strict",
                "combat_lethality": "deadly",
                "seed": 7331,
                "generated_class_summary": "Starter gear: Shortbow. Stats: strength 14, agility 12.",
            },
            "state": {
                "contract_version": "rpg_new_game_v1",
                "session_id": "rpg_test",
                "metadata": {
                    "kind": "new_game",
                    "campaign_template": "classic_fantasy",
                    "difficulty": "harsh",
                    "world_activity": "living_world",
                    "economy_pressure": "strict",
                    "combat_lethality": "deadly",
                    "initial_stats": {"strength": 14, "agility": 12},
                    "starter_gear": ["Shortbow", "10 gold"],
                    "seed": 7331,
                },
                "player": {
                    "inventory": [{"id": "shortbow", "name": "Shortbow", "quantity": 1}],
                    "currency": {"gold": 10, "silver": 0, "copper": 0},
                },
                "narrative_affordances": {"opening_story": {"opening_hook": "tavern_rumor"}},
                "mechanics": {"setup_effects": [{"id": "difficulty_harsh"}]},
                "quick_actions": ["Ask Bran about the rumor"],
            },
        },
    }


def test_wizard_new_game_validation_accepts_complete_prepared_session() -> None:
    validation = build_wizard_new_game_validation(_new_game_prepared(), required=True, turns_requested=100)

    assert validation["ok"] is True
    assert validation["status"] == "validated"
    assert validation["detected"] is True
    assert validation["failed_checks"] == []
    assert validation["session_id"] == "rpg_test"
    assert validation["turns_requested"] == 100
    assert validation["metadata"] == {
        "kind": "new_game",
        "created_from": "new_game",
        "campaign_template": "classic_fantasy",
        "difficulty": "harsh",
        "world_activity": "living_world",
        "economy_pressure": "strict",
        "combat_lethality": "deadly",
        "seed": 7331,
    }


def test_wizard_new_game_validation_keeps_legacy_autoplay_non_blocking() -> None:
    validation = build_wizard_new_game_validation(
        {"session_id": "legacy", "simulation_state": {"seed": 99}},
        required=False,
        turns_requested=20,
    )

    assert validation["ok"] is True
    assert validation["status"] == "not_detected"
    assert validation["detected"] is False
    assert validation["session_id"] == "legacy"
    assert "new_game_contract" in validation["failed_checks"]


def test_wizard_new_game_validation_can_be_required_for_100_turn_gate() -> None:
    validation = build_wizard_new_game_validation(
        {"session_id": "legacy", "simulation_state": {"seed": 99}},
        required=True,
        turns_requested=100,
    )

    assert validation["ok"] is False
    assert validation["status"] == "failed"
    assert validation["detected"] is False
    assert validation["required"] is True


def test_wizard_new_game_validation_fails_missing_authoritative_effects_when_required() -> None:
    prepared = _new_game_prepared()
    state = prepared["session"]["state"]  # type: ignore[index]
    state["mechanics"] = {"setup_effects": []}  # type: ignore[index]

    validation = build_wizard_new_game_validation(prepared, required=True, turns_requested=100)

    assert validation["ok"] is False
    assert validation["status"] == "failed"
    assert validation["detected"] is True
    assert "setting_effects_present" in validation["failed_checks"]
