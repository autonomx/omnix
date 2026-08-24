from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.trading.paper import (
    PaperAccount,
    PaperAccountSnapshot,
    PaperBalance,
    PaperOrderRequest,
)
from app.trading.replay_execution import (
    ReplayExecutionBar,
    advance_replay_snapshot,
    detached_replay_snapshot,
    place_replay_order,
)


def _snapshot() -> PaperAccountSnapshot:
    return PaperAccountSnapshot(
        account=PaperAccount(
            account_id="paper-1",
            name="Paper",
            base_currency="USD",
            commission_bps=Decimal("0"),
        ),
        balances=[PaperBalance(currency="USD", available=Decimal("1000"), reserved=Decimal("25"))],
        positions=[],
        open_orders=[],
        order_history=[],
        recent_fills=[],
        recent_ledger=[],
    )


def _bar(close: str, *, high: str | None = None, low: str | None = None) -> ReplayExecutionBar:
    value = Decimal(close)
    return ReplayExecutionBar(
        instrument_id="equity:NYSE:TEST",
        binding_id=None,
        start_time=datetime(2024, 1, 2, 10, 0, tzinfo=timezone.utc),
        end_time=datetime(2024, 1, 2, 11, 0, tzinfo=timezone.utc),
        open=value,
        high=Decimal(high or close),
        low=Decimal(low or close),
        close=value,
        volume=Decimal("100"),
    )


def test_replay_market_fill_uses_common_slippage_and_participation_policy() -> None:
    detached = detached_replay_snapshot(_snapshot())
    result = place_replay_order(
        detached,
        PaperOrderRequest(
            order_id="market-1",
            instrument_id="equity:NYSE:TEST",
            binding_id=None,
            side="buy",
            order_type="market",
            quantity=Decimal("20"),
            reference_price=Decimal("101"),
            idempotency_key="market-1",
        ),
        _bar("101"),
    )

    # 10% of the 100-share historical bar is executable and market slippage is 10 bps.
    assert result.order.status == "open"
    assert result.order.filled_quantity == Decimal("10")
    assert result.order.average_fill_price == Decimal("101.101")
    assert result.snapshot.positions[0].quantity == Decimal("10")


def test_replay_limit_waits_for_range_and_uses_common_decision_function() -> None:
    detached = detached_replay_snapshot(_snapshot())
    placed = place_replay_order(
        detached,
        PaperOrderRequest(
            order_id="limit-1",
            instrument_id="equity:NYSE:TEST",
            binding_id=None,
            side="buy",
            order_type="limit",
            quantity=Decimal("2"),
            limit_price=Decimal("90"),
            idempotency_key="limit-1",
        ),
        _bar("100"),
    )
    assert placed.order.status == "open"

    advanced = advance_replay_snapshot(placed.snapshot, _bar("92", high="95", low="89"))
    filled = next(order for order in advanced.order_history if order.order_id == "limit-1")
    assert filled.status == "filled"
    assert filled.average_fill_price == Decimal("90")


def test_detached_replay_state_does_not_inherit_live_reservations() -> None:
    detached = detached_replay_snapshot(_snapshot())
    assert detached.balances[0].available == Decimal("1025")
    assert detached.balances[0].reserved == Decimal("0")
    assert detached.open_orders == []
    assert detached.order_history == []
