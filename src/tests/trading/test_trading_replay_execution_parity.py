from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.trading.paper import (
    PaperAccount,
    PaperAccountSnapshot,
    PaperBalance,
    PaperExecutionPolicy,
    PaperMarketObservation,
    PaperOrder,
    PaperOrderRequest,
    paper_fill_decision,
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


def _bar(
    close: str,
    *,
    high: str | None = None,
    low: str | None = None,
    start_hour: int = 10,
) -> ReplayExecutionBar:
    value = Decimal(close)
    start = datetime(2024, 1, 2, start_hour, 0, tzinfo=timezone.utc)
    return ReplayExecutionBar(
        instrument_id="equity:NYSE:TEST",
        binding_id=None,
        start_time=start,
        end_time=start + timedelta(hours=1),
        open=value,
        high=Decimal(high or close),
        low=Decimal(low or close),
        close=value,
        volume=Decimal("100"),
    )


def test_replay_market_waits_for_post_activation_bar_volume() -> None:
    funded = _snapshot().model_copy(
        update={"balances": [PaperBalance(currency="USD", available=Decimal("10000"), reserved=Decimal("0"))]}
    )
    detached = detached_replay_snapshot(funded)
    placed = place_replay_order(
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

    # The placement bar's volume predates activation and cannot be consumed.
    assert placed.order.status == "open"
    assert placed.order.filled_quantity == Decimal("0")
    assert placed.snapshot.positions == []

    advanced = advance_replay_snapshot(placed.snapshot, _bar("101", start_hour=11))
    filled = next(order for order in advanced.order_history if order.order_id == "market-1")
    # 10% of the first fully post-activation 100-share bar is executable;
    # paper-execution-v2 then applies the common 10 bps market slippage.
    assert filled.status == "open"
    assert filled.filled_quantity == Decimal("10")
    assert filled.average_fill_price == Decimal("101.101")
    assert advanced.positions[0].quantity == Decimal("10")


def test_same_bar_range_before_activation_cannot_trigger_new_order() -> None:
    policy = PaperExecutionPolicy(latency_ms=250)
    created = datetime(2024, 1, 2, 10, 59, 59, 500000, tzinfo=timezone.utc)
    order = PaperOrder(
        account_id="paper-1",
        order_id="limit-causal",
        instrument_id="equity:NYSE:TEST",
        side="buy",
        order_type="limit",
        quantity=Decimal("1"),
        limit_price=Decimal("90"),
        idempotency_key="limit-causal",
        created_at=created,
    )
    observation = PaperMarketObservation(
        instrument_id="equity:NYSE:TEST",
        provider="fixture",
        price=Decimal("100"),
        ask=Decimal("100"),
        ask_size=Decimal("100"),
        high=Decimal("105"),
        low=Decimal("89"),
        bar_start_time=datetime(2024, 1, 2, 10, 0, tzinfo=timezone.utc),
        source_time=datetime(2024, 1, 2, 11, 0, tzinfo=timezone.utc),
        evaluated_at=datetime(2024, 1, 2, 11, 0, tzinfo=timezone.utc),
    )

    decision = paper_fill_decision(order, observation, policy)
    assert decision.should_fill is False
    assert decision.reason == "limit_range_not_reached"


def test_replay_limit_waits_for_next_causal_range() -> None:
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
        _bar("100", high="105", low="89"),
    )
    assert placed.order.status == "open"
    assert placed.order.filled_quantity == Decimal("0")

    advanced = advance_replay_snapshot(
        placed.snapshot,
        _bar("92", high="95", low="89", start_hour=11),
    )
    filled = next(order for order in advanced.order_history if order.order_id == "limit-1")
    assert filled.status == "filled"
    assert filled.average_fill_price == Decimal("90")


def test_detached_replay_state_does_not_inherit_live_reservations() -> None:
    detached = detached_replay_snapshot(_snapshot())
    assert detached.balances[0].available == Decimal("1025")
    assert detached.balances[0].reserved == Decimal("0")
    assert detached.open_orders == []
    assert detached.order_history == []
