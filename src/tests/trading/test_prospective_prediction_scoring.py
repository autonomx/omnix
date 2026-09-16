from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.trading.models import AdjustmentMode, MarketBar
from app.trading.prospective_prediction_evidence import SIPTradeEvent, select_analysis_session_prices
from app.trading.prospective_prediction_scoring import build_formal_outcome_labels

UTC = timezone.utc
SESSION = date(2026, 9, 16)
OPEN = datetime(2026, 9, 16, 13, 30, tzinfo=UTC)
CLOSE = datetime(2026, 9, 16, 20, 0, tzinfo=UTC)
INSTRUMENT = "equity:NASDAQ:TEST"


def _prices():
    return select_analysis_session_prices(
        [
            SIPTradeEvent(
                instrument_id=INSTRUMENT,
                price=Decimal("10"),
                event_timestamp=OPEN,
                received_timestamp=OPEN + timedelta(milliseconds=1),
                provider_event_id="open",
                sequence=1,
            ),
            SIPTradeEvent(
                instrument_id=INSTRUMENT,
                price=Decimal("12"),
                event_timestamp=CLOSE - timedelta(milliseconds=1),
                received_timestamp=CLOSE + timedelta(milliseconds=1),
                provider_event_id="close",
                sequence=2,
            ),
        ],
        session_date=SESSION,
        outcome_state="FINAL",
    )


def _bar(*, interval: str, index: int, close: str, minutes: int) -> MarketBar:
    start = OPEN + timedelta(minutes=minutes * index)
    value = Decimal(close)
    return MarketBar(
        instrument_id=INSTRUMENT,
        interval=interval,
        start_time=start,
        end_time=start + timedelta(minutes=minutes),
        open=value - Decimal("0.01"),
        high=value + Decimal("0.02"),
        low=value - Decimal("0.03"),
        close=value,
        volume=Decimal("1000"),
        is_final=True,
        adjustment_mode=AdjustmentMode.RAW,
        session="regular",
        provider="alpaca_sip",
        provider_sequence=index,
        received_at=start + timedelta(minutes=minutes, seconds=1),
    )


def test_formal_scoring_ignores_mixed_1m_bars_and_uses_only_5m() -> None:
    five_minute = [
        _bar(interval="5m", index=i, close=str(Decimal("10.1") + Decimal(i) * Decimal("0.025")), minutes=5)
        for i in range(78)
    ]
    # Deliberately bearish 1m data must not alter the formal 5m label.
    one_minute = [
        _bar(interval="1m", index=i, close=str(Decimal("10") - Decimal(i) * Decimal("0.01")), minutes=1)
        for i in range(60)
    ]

    measurements, labels = build_formal_outcome_labels(
        prices=_prices(),
        bars=[*one_minute, *five_minute],
    )

    assert measurements.observed_bar_count == 78
    assert labels.persistent_uptrend is True


def test_formal_scoring_fails_closed_without_5m_data() -> None:
    with pytest.raises(ValueError, match="requires_raw_final_5m_bars"):
        build_formal_outcome_labels(
            prices=_prices(),
            bars=[_bar(interval="1m", index=0, close="10.1", minutes=1)],
        )
