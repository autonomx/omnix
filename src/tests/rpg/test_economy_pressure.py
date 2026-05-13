from app.rpg.economy.economy_pressure import EconomyPressureRule, apply_economy_pressure


def test_economy_pressure_deducts_currency_when_due():
    result = apply_economy_pressure(
        economy_state={"currency": {"gold": 5}},
        turn_index=10,
        rules=[
            EconomyPressureRule(
                id="economy:test",
                kind="upkeep",
                every_turns=5,
                cost_currency=("gold", 2),
                event={"summary": "Upkeep."},
            )
        ],
    )

    assert result["event_count"] == 1
    assert result["currency"]["gold"] == 3
    assert result["events"][0]["paid"] is True
    assert result["currency_deltas"][0]["delta"] == -2


def test_economy_pressure_warns_when_insufficient_currency():
    result = apply_economy_pressure(
        economy_state={"currency": {"gold": 1}},
        turn_index=10,
        rules=[
            EconomyPressureRule(
                id="economy:test",
                kind="upkeep",
                every_turns=5,
                cost_currency=("gold", 2),
                event={"summary": "Upkeep."},
            )
        ],
    )

    assert result["event_count"] == 1
    assert result["currency"]["gold"] == 1
    assert result["events"][0]["paid"] is False
    assert result["warnings"][0]["subtype"] == "insufficient_currency"


def test_economy_pressure_respects_due_interval():
    result = apply_economy_pressure(
        economy_state={"currency": {"gold": 5}},
        turn_index=11,
        rules=[
            EconomyPressureRule(
                id="economy:test",
                kind="upkeep",
                every_turns=5,
                cost_currency=("gold", 2),
            )
        ],
    )

    assert result["event_count"] == 0
    assert result["currency"]["gold"] == 5