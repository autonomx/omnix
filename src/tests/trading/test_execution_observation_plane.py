from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.trading.execution import ExecutionObservation
from app.trading.execution_observation_plane import ExecutionObservationPlane


INSTRUMENT = "equity:NASDAQ:TEST"


def _observation(source_time: datetime, *, received_at: datetime, price: str) -> ExecutionObservation:
    value = Decimal(price)
    return ExecutionObservation(
        instrument_id=INSTRUMENT,
        binding_id="equity:TEST:live",
        provider="alpaca_iex",
        bid=value - Decimal("0.01"),
        ask=value + Decimal("0.01"),
        last=value,
        source_time=source_time,
        received_at=received_at,
        session="regular",
        freshness_mode="live",
        execution_eligible=True,
    )


def test_first_causal_after_never_backfills_predecision_quote():
    plane = ExecutionObservationPlane()
    decision = datetime(2026, 9, 17, 14, 2, 0, tzinfo=timezone.utc)
    before = _observation(
        decision - timedelta(milliseconds=200),
        received_at=decision - timedelta(milliseconds=100),
        price="1.86",
    )
    after = _observation(
        decision + timedelta(milliseconds=250),
        received_at=decision + timedelta(milliseconds=350),
        price="1.88",
    )
    plane.record(before, recorded_at=before.received_at)
    plane.record(after, recorded_at=after.received_at)

    selected = plane.first_causal_after(
        INSTRUMENT,
        decision_completed_at=decision,
        market_snapshot_as_of=decision - timedelta(seconds=2),
    )
    assert selected is not None
    assert selected.observation.last == Decimal("1.88")
    assert selected.quote_source_at > decision
    assert selected.capture_lag_seconds == Decimal("0.35")


def test_no_postdecision_quote_means_no_causal_fill_candidate():
    plane = ExecutionObservationPlane()
    decision = datetime(2026, 9, 17, 14, 2, tzinfo=timezone.utc)
    observation = _observation(
        decision - timedelta(seconds=1),
        received_at=decision - timedelta(milliseconds=500),
        price="1.86",
    )
    plane.record(observation, recorded_at=observation.received_at)
    assert plane.first_causal_after(
        INSTRUMENT,
        decision_completed_at=decision,
    ) is None
