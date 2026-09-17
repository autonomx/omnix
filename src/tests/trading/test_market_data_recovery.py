from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.trading.market_data_recovery import recover_market_bars
from app.trading.models import MarketBar


ET = ZoneInfo("America/New_York")
INSTRUMENT = "equity:NASDAQ:TEST"


def _bar(start_et: datetime, *, provider: str = "primary") -> MarketBar:
    start = start_et.astimezone(timezone.utc)
    return MarketBar(
        instrument_id=INSTRUMENT,
        interval="1m",
        start_time=start,
        end_time=start + timedelta(minutes=1),
        open=Decimal("10"),
        high=Decimal("10.1"),
        low=Decimal("9.9"),
        close=Decimal("10"),
        volume=Decimal("100"),
        provider=provider,
        session="regular",
    )


def test_general_recovery_fills_exact_gap_from_fallback_without_synthetic_bar():
    start = datetime(2026, 9, 17, 9, 30, tzinfo=ET)
    primary = [_bar(start), _bar(start + timedelta(minutes=2))]
    fallback = [_bar(start + timedelta(minutes=1), provider="fallback")]
    result = recover_market_bars(
        instrument_id=INSTRUMENT,
        interval="1m",
        session_date=start.date(),
        observed_at=start + timedelta(minutes=3, seconds=10),
        primary_fetch=lambda: primary,
        primary_source="primary",
        fallback_fetch=lambda: fallback,
        fallback_source="fallback",
    )
    assert result.status == "COMPLETE"
    assert len(result.bars) == 3
    assert result.unresolved_starts == ()
    assert set(result.source_providers) == {"primary", "fallback"}


def test_unresolved_gap_remains_partial():
    start = datetime(2026, 9, 17, 9, 30, tzinfo=ET)
    result = recover_market_bars(
        instrument_id=INSTRUMENT,
        interval="1m",
        session_date=start.date(),
        observed_at=start + timedelta(minutes=3),
        primary_fetch=lambda: [_bar(start)],
        primary_source="primary",
    )
    assert result.status == "PARTIAL"
    assert len(result.unresolved_starts) == 2
