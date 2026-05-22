from __future__ import annotations

from app.rpg.session.survival_autoplay_persistence import (
    extract_turn_survival_state,
    mirror_survival_state_into_session,
    persist_result_survival_state,
)


def _result():
    return {
        "turn_contract": {
            "climate_survival": {
                "format_version": "n1231_climate_survival_state_v1",
                "runtime_enforced": True,
                "source": "deterministic_authoritative_turn_tick",
                "tick": 72,
                "survival": {
                    "hunger": 72,
                    "thirst": 74,
                    "fatigue": 71,
                    "action_count": 72,
                    "warnings": ["hunger_high", "thirst_high", "fatigue_high"],
                },
            }
        },
        "session": {
            "simulation_state": {
                "player_state": {
                    "resources": {"hunger": 2, "thirst": 3, "fatigue": 2},
                    "inventory_state": {"items": []},
                },
                "needs": {"hunger": 2, "thirst": 3, "fatigue": 2},
            },
            "runtime_state": {},
            "state": {},
            "setup_payload": {"metadata": {}},
        },
    }


def test_n1272_extracts_authoritative_turn_survival_state() -> None:
    climate = extract_turn_survival_state(_result())

    assert climate["tick"] == 72
    assert climate["survival"]["hunger"] == 72
    assert climate["survival"]["thirst"] == 74
    assert climate["survival"]["fatigue"] == 71
    assert climate["runtime_enforced"] is True


def test_n1272_mirrors_survival_state_into_all_session_roots() -> None:
    result = _result()
    climate = extract_turn_survival_state(result)
    session = mirror_survival_state_into_session(result["session"], climate)

    assert session["simulation_state"]["needs"] == {"hunger": 72, "thirst": 74, "fatigue": 71}
    assert session["simulation_state"]["player_state"]["resources"]["thirst"] == 74
    assert session["runtime_state"]["climate_survival"]["survival"]["fatigue"] == 71
    assert session["state"]["needs"] == {"hunger": 72, "thirst": 74, "fatigue": 71}
    assert session["setup_payload"]["metadata"]["needs"] == {"hunger": 72, "thirst": 74, "fatigue": 71}


def test_n1272_persist_result_survival_state_updates_return_payload_without_save() -> None:
    result = persist_result_survival_state(_result(), save=False)

    assert result["survival_autoplay_persistence"]["applied"] is True
    assert result["session"]["simulation_state"]["needs"]["hunger"] == 72
    assert result["simulation_state"]["needs"]["thirst"] == 74
