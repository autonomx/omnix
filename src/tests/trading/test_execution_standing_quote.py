"""A live IBKR line's standing quote prices a V3 entry (owner decision 2026-11-12)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.apps.trading.execution import ExecutionObservation, assess_execution_observation
from app.apps.trading.execution_observation_plane import (
    STANDING_QUOTE_MAX_AGE_SECONDS,
    ExecutionObservationPlane,
    first_causal_execution,
)
from app.apps.trading.paper import PaperExecutionPolicy
from app.apps.trading.strategy_ai_shadow import simulate_ai_shadow_fill


INSTRUMENT = "equity:NASDAQ:TCRT"
BINDING = "ibkr:TCRT"
ACTIONABLE_AT = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)
LATENCY = Decimal(PaperExecutionPolicy().latency_ms) / 1000  # the order becomes active 0.25 s on


def _at(seconds: float) -> datetime:
    return ACTIONABLE_AT + timedelta(seconds=seconds)


def _quote(plane, *, seconds, bid="2.90", ask="2.92", provider="ibkr", purpose="LIVE_DATA", binding=BINDING):
    source_time = _at(seconds)
    observation = assess_execution_observation(
        ExecutionObservation(
            instrument_id=INSTRUMENT,
            binding_id=binding,
            provider=provider,
            binding_purpose=purpose,
            bid=Decimal(bid),
            ask=Decimal(ask),
            last=Decimal("2.91"),
            source_time=source_time,
            received_at=source_time + timedelta(milliseconds=200),
            session="regular",
            freshness_mode="live",
            market_data_type="LIVE",
            live_entitled=True,
        ),
        binding_purpose=purpose,
    )
    plane.record(observation, recorded_at=source_time + timedelta(milliseconds=300))


def _confirm(plane, *, up_since, confirmed_at, binding=BINDING):
    plane.confirm_line(INSTRUMENT, binding_id=binding, up_since=_at(up_since), confirmed_at=_at(confirmed_at))


def _select(plane, *, now=10.0, decision_completed=0.0, ibkr_live=True):
    return first_causal_execution(
        plane,
        INSTRUMENT,
        decision_completed_at=_at(decision_completed),
        actionable_at=ACTIONABLE_AT,
        market_snapshot_as_of=ACTIONABLE_AT,
        binding_id="alpaca_iex:TCRT",
        ibkr_live=ibkr_live,
        standing_max_age_seconds=STANDING_QUOTE_MAX_AGE_SECONDS,
        standing_latency_seconds=LATENCY,
        now=_at(now),
    )


def test_a_quiet_live_line_prices_the_entry_from_the_quote_standing_at_the_trigger():
    plane = ExecutionObservationPlane()
    _quote(plane, seconds=-20, bid="2.90", ask="2.92")
    _quote(plane, seconds=40, bid="3.10", ask="3.12")  # the first quote after: never used
    _confirm(plane, up_since=-60, confirmed_at=-15)
    _confirm(plane, up_since=-60, confirmed_at=5)

    selected = _select(plane)
    assert selected.selection_basis == "standing"
    assert selected.observation.bid == Decimal("2.90")
    assert selected.priced_at == _at(0.25)
    assert selected.quote_age_seconds == Decimal("20.25")
    assert selected.first_post_decision_quote_at == _at(5)  # the line check that proved it
    assert selected.capture_lag_seconds == 0

    # The fill simulation accepts it, priced as the book standing when the order was active
    # (as the V3 monitor passes it); the quote's own time would predate the order.
    execution = selected.observation.model_dump(mode="python")
    execution["source_time"] = selected.priced_at
    fill = simulate_ai_shadow_fill(
        execution,
        side="buy",
        instrument_id=INSTRUMENT,
        binding_id=BINDING,
        decision_at=ACTIONABLE_AT,
        requested_units=Decimal("1"),
        reference_price=Decimal("2.91"),
        max_capture_lag_seconds=Decimal("10"),
    )
    assert fill.should_fill, fill.fill_reason
    assert fill.fill_price >= Decimal("2.92")  # the standing ask, plus the policy's slippage


def test_a_book_older_than_thirty_seconds_falls_back_to_the_first_quote_after():
    plane = ExecutionObservationPlane()
    _quote(plane, seconds=-31, bid="2.90", ask="2.92")
    _quote(plane, seconds=4, bid="2.95", ask="2.97")
    _confirm(plane, up_since=-60, confirmed_at=5)

    selected = _select(plane)
    assert selected.selection_basis == "first_after"
    assert selected.observation.bid == Decimal("2.95")


def test_the_quote_never_predates_the_decision_when_the_decision_came_last():
    plane = ExecutionObservationPlane()
    _quote(plane, seconds=-10, bid="2.90", ask="2.92")
    _quote(plane, seconds=30, bid="3.00", ask="3.02")  # stands when the decision completes at +38 s
    _confirm(plane, up_since=-60, confirmed_at=40)

    selected = _select(plane, decision_completed=38, now=45)
    assert selected.selection_basis == "standing"
    assert selected.observation.bid == Decimal("3.00")
    assert selected.quote_age_seconds == Decimal("8.25")


def test_without_a_line_check_after_the_trigger_the_selection_waits_then_falls_back():
    plane = ExecutionObservationPlane()
    _quote(plane, seconds=-5)
    _confirm(plane, up_since=-60, confirmed_at=-2)

    assert _select(plane, now=3) is None  # pending: the next check decides
    late = _select(plane, now=20)  # no check came; the old rule applies (no quote after)
    assert late is None or late.selection_basis == "first_after"


def test_a_line_that_broke_after_the_quote_cannot_vouch_for_it():
    plane = ExecutionObservationPlane()
    _quote(plane, seconds=-5, bid="2.90", ask="2.92")
    _quote(plane, seconds=6, bid="2.99", ask="3.01")
    # The line came back up at -1 s, after the standing quote was recorded.
    _confirm(plane, up_since=-1, confirmed_at=5)

    selected = _select(plane, now=8)
    assert selected.selection_basis == "first_after"
    assert selected.observation.bid == Decimal("2.99")


def test_an_unconfirmed_line_and_the_live_data_gate_keep_the_old_rule():
    plane = ExecutionObservationPlane()
    _quote(plane, seconds=-5)
    assert _select(plane, now=20) is None  # never confirmed: no standing fill, no quote after

    _confirm(plane, up_since=-60, confirmed_at=5)
    assert _select(plane, ibkr_live=False) is None  # IEX path only, and it has no quote


def test_a_check_on_another_binding_does_not_vouch_for_the_quote():
    plane = ExecutionObservationPlane()
    _quote(plane, seconds=-5)
    _confirm(plane, up_since=-60, confirmed_at=5, binding="ibkr:OTHER")
    assert _select(plane, now=20) is None
