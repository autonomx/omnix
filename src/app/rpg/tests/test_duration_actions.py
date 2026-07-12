from app.rpg.session.duration_actions import apply_duration_action, duration_minutes
from app.rpg.session.public_state_bridge import synchronize_player_projections
from app.rpg.economy.service_resolver import resolve_service_turn
from app.rpg.session.service_runtime import service_action_from_result, service_authoritative_result


def _lodging_session() -> dict:
    return synchronize_player_projections(
        {
            "state": {
                "player": {"currency": {"gold": 0, "silver": 5, "copper": 0}},
                "world": {
                    "time": "Day 1 • 20:30",
                    "environment": {"absolute_minutes": 20 * 60 + 30, "active_events": []},
                },
            },
            "simulation_state": {
                "active_services": [
                    {
                        "service_id": "lodging:test",
                        "service_kind": "lodging",
                        "status": "active",
                        "effects": {"duration": "one_night", "rest_quality": "basic"},
                    }
                ],
                "survival": {"enabled": True, "hunger": 10, "thirst": 10, "fatigue": 70},
            },
            "runtime_state": {},
        }
    )


def test_one_night_advances_to_next_morning_and_consumes_service() -> None:
    session = _lodging_session()

    result = apply_duration_action(
        session["simulation_state"],
        player_input="I sleep through the night until morning.",
        service_kind="lodging",
        tick=9,
    )
    projected = synchronize_player_projections(session)

    assert result["applied"] is True
    assert result["elapsed_minutes"] == 11 * 60 + 30
    assert result["environment_after"]["absolute_minutes"] == 32 * 60
    assert result["active_service"]["status"] == "consumed"
    assert projected["state"]["world"]["time"] == "Day 2 • 08:00"
    assert projected["simulation_state"]["survival"]["fatigue"] == 15


def test_duration_action_requires_active_service() -> None:
    result = apply_duration_action(
        {"environment": {"absolute_minutes": 20 * 60}},
        player_input="I sleep until morning.",
        service_kind="lodging",
        tick=2,
    )

    assert result["applied"] is False
    assert result["blocked_reason"] == "missing_active_service"


def test_buying_lodging_without_sleep_request_does_not_advance_time() -> None:
    session = _lodging_session()

    result = apply_duration_action(
        session["simulation_state"],
        player_input="I reserve the room.",
        service_kind="lodging",
        tick=2,
    )

    assert result["applied"] is False
    assert result["blocked_reason"] == "duration_not_requested"
    assert session["simulation_state"]["environment"]["absolute_minutes"] == 20 * 60 + 30


def test_explicit_minute_policy_is_reusable_for_other_services() -> None:
    assert duration_minutes({}, "minutes:90") == 90


def test_lodging_purchase_and_explicit_sleep_apply_as_one_atomic_sequence() -> None:
    session = _lodging_session()
    session["simulation_state"]["active_services"] = []
    service_result = resolve_service_turn(
        player_input="I buy the common room cot from Bran and sleep until morning.",
        action={},
        resolved_action={},
        simulation_state=session["simulation_state"],
        runtime_state={"tick": 9},
    )
    action = service_action_from_result(
        "I buy the common room cot from Bran and sleep until morning.",
        {},
        service_result,
    )

    authoritative = service_authoritative_result(session["simulation_state"], action)

    result = authoritative["result"]
    assert result["purchase_applied"] is True
    assert result["duration_application"]["applied"] is True
    assert result["service_application"]["currency_after"] == {
        "gold": 0,
        "silver": 0,
        "copper": 0,
    }
    assert authoritative["simulation_state"]["environment"]["absolute_minutes"] == 32 * 60
