from app.rpg.social.leverage import add_social_leverage, validate_leverage


def test_valid_leverage_returns_bonus():
    simulation_state = {}
    add_social_leverage(
        simulation_state,
        {
            "leverage_id": "lev:bran_debt",
            "npc_id": "bran",
            "kind": "debt",
            "summary": "Bran owes the player a favor.",
            "strength": 25,
            "valid": True,
            "tags": ["favor", "room"],
        },
    )

    result = validate_leverage(
        simulation_state,
        "bran",
        "lev:bran_debt",
        request="discounted room",
    )

    assert result["ok"] is True
    assert result["bonus"] == 25


def test_invalid_leverage_is_rejected():
    simulation_state = {}
    add_social_leverage(
        simulation_state,
        {
            "leverage_id": "lev:fake",
            "npc_id": "bran",
            "kind": "secret",
            "summary": "Fake leverage.",
            "strength": 50,
            "valid": False,
        },
    )

    result = validate_leverage(simulation_state, "bran", "lev:fake")

    assert result["ok"] is False
    assert result["reason"] == "invalid"


def test_missing_leverage_is_rejected():
    result = validate_leverage({}, "bran", "lev:missing")

    assert result["ok"] is False
    assert result["reason"] == "missing"