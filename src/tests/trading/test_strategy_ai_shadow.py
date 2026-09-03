from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.trading.strategy_ai_shadow import (
    AIShadowDecision,
    AIShadowPolicyAnalyzer,
    AIShadowPositionState,
    apply_fill,
    desired_fill,
    event_trigger_reasons,
    simulate_ai_shadow_fill,
)


INSTRUMENT = "equity:NASDAQ:TEST"
DECISION_AT = datetime(2026, 9, 3, 14, 0, tzinfo=timezone.utc)


def _decision(action: str) -> AIShadowDecision:
    return AIShadowDecision(
        instrument_id=INSTRUMENT,
        action=action,
        confidence=80,
        market_regime="trend_continuation",
        expected_horizon_minutes=60,
        thesis="Trend remains intact.",
        reason="Higher lows and VWAP support remain intact.",
        invalidation_price=Decimal("9.50"),
    )


def _execution(*, bid: str, ask: str, last: str = "10"):
    return {
        "provider": "alpaca_iex",
        "last": Decimal(last),
        "bid": Decimal(bid),
        "ask": Decimal(ask),
        "bid_size": Decimal("1000"),
        "ask_size": Decimal("1000"),
        "source_time": DECISION_AT + timedelta(seconds=2),
        "spread_bps": (
            (Decimal(ask) - Decimal(bid))
            / ((Decimal(ask) + Decimal(bid)) / Decimal("2"))
            * Decimal("10000")
        ),
        "execution_eligible": True,
        "freshness_mode": "live",
        "rejection_reasons": (),
        "halted": False,
    }


def test_normalized_position_actions_are_bounded() -> None:
    flat = AIShadowPositionState(policy="minute", instrument_id=INSTRUMENT)
    assert desired_fill(_decision("enter"), flat) == ("buy", Decimal("1"))
    assert desired_fill(_decision("add"), flat) == (None, Decimal("0"))

    long = flat.model_copy(
        update={"normalized_units": Decimal("1"), "average_cost": Decimal("10")}
    )
    assert desired_fill(_decision("add"), long) == ("buy", Decimal("0.5"))
    assert desired_fill(_decision("reduce"), long) == ("sell", Decimal("0.5"))
    assert desired_fill(_decision("exit"), long) == ("sell", Decimal("1"))

    maxed = long.model_copy(update={"normalized_units": Decimal("1.5")})
    assert desired_fill(_decision("add"), maxed) == (None, Decimal("0"))


def test_ai_fill_uses_ask_for_buy_and_bid_for_sell_with_slippage() -> None:
    buy = simulate_ai_shadow_fill(
        _execution(bid="9.95", ask="10.05"),
        side="buy",
        instrument_id=INSTRUMENT,
        binding_id="alpaca:TEST",
        decision_at=DECISION_AT,
        requested_units=Decimal("1"),
        reference_price=Decimal("10"),
    )
    sell = simulate_ai_shadow_fill(
        _execution(bid="10.95", ask="11.05", last="11"),
        side="sell",
        instrument_id=INSTRUMENT,
        binding_id="alpaca:TEST",
        decision_at=DECISION_AT,
        requested_units=Decimal("1"),
        reference_price=Decimal("11"),
    )

    assert buy.should_fill is True
    assert sell.should_fill is True
    assert buy.fill_price == Decimal("10.05") * Decimal("1.001")
    assert sell.fill_price == Decimal("10.95") * Decimal("0.999")


def test_position_state_tracks_add_reduce_and_realized_pnl() -> None:
    state = AIShadowPositionState(policy="minute", instrument_id=INSTRUMENT)
    entry = simulate_ai_shadow_fill(
        _execution(bid="9.95", ask="10.05"),
        side="buy",
        instrument_id=INSTRUMENT,
        binding_id="alpaca:TEST",
        decision_at=DECISION_AT,
        requested_units=Decimal("1"),
        reference_price=Decimal("10"),
    )
    state = apply_fill(state, entry, trade_id="trade-1")
    assert state.normalized_units == Decimal("1")
    assert state.average_cost == entry.fill_price

    add = simulate_ai_shadow_fill(
        _execution(bid="10.45", ask="10.55", last="10.5"),
        side="buy",
        instrument_id=INSTRUMENT,
        binding_id="alpaca:TEST",
        decision_at=DECISION_AT,
        requested_units=Decimal("0.5"),
        reference_price=Decimal("10.5"),
    )
    state = apply_fill(state, add, trade_id="trade-1")
    assert state.normalized_units == Decimal("1.5")

    reduce = simulate_ai_shadow_fill(
        _execution(bid="10.95", ask="11.05", last="11"),
        side="sell",
        instrument_id=INSTRUMENT,
        binding_id="alpaca:TEST",
        decision_at=DECISION_AT,
        requested_units=Decimal("0.5"),
        reference_price=Decimal("11"),
    )
    before_realized = state.realized_pnl
    state = apply_fill(state, reduce, trade_id="trade-1")
    assert state.normalized_units == Decimal("1")
    assert state.realized_pnl > before_realized

    exit_fill = simulate_ai_shadow_fill(
        _execution(bid="11.45", ask="11.55", last="11.5"),
        side="sell",
        instrument_id=INSTRUMENT,
        binding_id="alpaca:TEST",
        decision_at=DECISION_AT,
        requested_units=Decimal("1"),
        reference_price=Decimal("11.5"),
    )
    state = apply_fill(state, exit_fill, trade_id="trade-1")
    assert state.normalized_units == 0
    assert state.average_cost is None
    assert state.realized_pnl > 0
    assert state.execution_drag_dollars > 0


def test_event_policy_triggers_only_on_material_changes() -> None:
    base = {
        "deterministic": {"state": "second_pullback"},
        "learning": {"pattern": "unresolved"},
        "market": {
            "current_price": "10",
            "session_vwap": "10.2",
            "session_high": "11",
            "current_volume_ratio_to_prior10": "1.0",
        },
        "execution": {
            "spread_bps": "40",
            "execution_eligible": True,
            "halted": False,
        },
        "indicators": {
            "one_minute": {
                "stochastic_rsi_k": "50",
                "stochastic_rsi_d": "50",
                "ema9_rising": True,
            }
        },
        "position": {"unrealized_pct": "0"},
    }
    assert event_trigger_reasons(base, None) == ("initial",)
    assert event_trigger_reasons(base, base) == ()

    changed = {
        **base,
        "deterministic": {"state": "entry_ready"},
        "market": {
            **base["market"],
            "current_price": "10.4",
            "session_vwap": "10.2",
            "session_high": "11.2",
            "current_volume_ratio_to_prior10": "2.0",
        },
        "indicators": {
            "one_minute": {
                "stochastic_rsi_k": "10",
                "stochastic_rsi_d": "12",
                "ema9_rising": False,
            }
        },
    }
    reasons = event_trigger_reasons(changed, base)
    assert "deterministic_state_changed" in reasons
    assert "vwap_side_changed" in reasons
    assert "new_session_high" in reasons
    assert "volume_spike" in reasons
    assert "stoch_entered_oversold" in reasons
    assert "ema9_direction_changed" in reasons


class _Response:
    content = """{"decisions":[{"instrument_id":"equity:NASDAQ:TEST","action":"enter","confidence":82,"market_regime":"failed_selloff","expected_horizon_minutes":75,"thesis":"The flush recovered above VWAP.","reason":"Higher low plus improving momentum.","invalidation_price":"9.50","execution_authority":false}]}"""
    usage = {"prompt_tokens": 120, "completion_tokens": 40, "total_tokens": 160}
    model = "fixture-ai"


class _Provider:
    provider_name = "fixture"
    config = type("Config", (), {"model": "fixture-ai"})()

    def chat_completion(self, **kwargs):
        return _Response()


def test_ai_policy_analyzer_returns_strict_stateful_trade_decision() -> None:
    analyzer = AIShadowPolicyAnalyzer(provider_factory=lambda: _Provider())
    result = analyzer.assess(
        policy="minute",
        rows=[
            {
                "instrument_id": INSTRUMENT,
                "observed_at": DECISION_AT.isoformat(),
                "trigger_reasons": ["completed_1m_bar"],
                "feature_snapshot": {"market": {"current_price": "10"}},
                "previous_decision": None,
                "previous_feature_snapshot": None,
            }
        ],
    )

    assert result.policy == "minute"
    assert result.provider == "fixture"
    assert result.total_tokens == 160
    assert len(result.decisions) == 1
    assert result.decisions[0].action == "enter"
    assert result.decisions[0].invalidation_price == Decimal("9.50")
    assert result.decisions[0].execution_authority is False
