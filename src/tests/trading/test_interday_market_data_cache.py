from datetime import datetime, timezone
from decimal import Decimal

from scripts.trade.run_interday_winner_shadow_replay import (
    MarketDataCache,
    RawBar,
    cache_stats,
    reset_cache_stats,
)


UTC = timezone.utc


def _bar(start: datetime, *, interval_minutes: int) -> RawBar:
    return RawBar(
        start=start,
        open=Decimal("1"),
        high=Decimal("2"),
        low=Decimal("0.5"),
        close=Decimal("1.5"),
        volume=Decimal("10"),
        interval_minutes=interval_minutes,
    )


def test_market_data_cache_is_keyed_by_source_symbol_session_and_timeframe(tmp_path) -> None:
    reset_cache_stats()
    cache = MarketDataCache(tmp_path, "alpaca-sip")
    start = datetime(2026, 8, 13, 13, 30, tzinfo=UTC)
    end = datetime(2026, 8, 15, 20, 0, tzinfo=UTC)
    bars = (
        _bar(datetime(2026, 8, 13, 13, 30, tzinfo=UTC), interval_minutes=1),
        _bar(datetime(2026, 8, 14, 13, 30, tzinfo=UTC), interval_minutes=1),
    )

    cache.store(
        "CELU",
        "1m",
        bars,
        start=start,
        end=end,
        query_profile="regular_session",
    )

    first_session = tmp_path / "alpaca-sip" / "CELU" / "1m" / "2026-08-13.json"
    second_session = tmp_path / "alpaca-sip" / "CELU" / "1m" / "2026-08-14.json"
    assert first_session.exists()
    assert second_session.exists()
    assert cache.load(
        "CELU",
        "1m",
        start=start,
        end=end,
        query_profile="regular_session",
    ) == bars
    assert cache_stats()["hits"] == 1

    assert cache.load(
        "OTHER",
        "1m",
        start=start,
        end=end,
        query_profile="regular_session",
    ) is None
    assert cache_stats()["misses"] == 1


def test_market_data_cache_miss_does_not_accept_a_different_request_range(tmp_path) -> None:
    cache = MarketDataCache(tmp_path, "alpaca-sip")
    start = datetime(2026, 8, 13, 13, 30, tzinfo=UTC)
    end = datetime(2026, 8, 14, 20, 0, tzinfo=UTC)
    cache.store(
        "CELU",
        "5m",
        (_bar(start, interval_minutes=5),),
        start=start,
        end=end,
        query_profile="extended_session",
    )

    assert cache.load(
        "CELU",
        "5m",
        start=start,
        end=end.replace(day=15),
        query_profile="extended_session",
    ) is None
