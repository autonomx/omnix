from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from scripts.trade.run_interday_winner_shadow_replay import (
    MarketDataCache,
    RawBar,
    _needs_one_minute_recovery,
    _recover_one_minute_sessions,
    _yahoo_1m_chunks,
)


UTC = timezone.utc
SESSION = date(2026, 9, 16)
OPEN = datetime(2026, 9, 16, 13, 30, tzinfo=UTC)  # 09:30 ET


def _bar(minute: int, *, interval_minutes: int = 1, price: str = "10") -> RawBar:
    value = Decimal(price)
    return RawBar(
        start=OPEN + timedelta(minutes=minute),
        open=value,
        high=value + Decimal("0.10"),
        low=value - Decimal("0.10"),
        close=value + Decimal("0.05"),
        volume=Decimal("1000"),
        interval_minutes=interval_minutes,
    )


def test_yahoo_one_minute_chunks_cover_the_requested_current_session() -> None:
    assert _yahoo_1m_chunks(SESSION, SESSION) == (
        (date(2026, 9, 16), date(2026, 9, 17)),
    )


def test_yahoo_one_minute_chunks_are_dynamic_and_bounded() -> None:
    chunks = _yahoo_1m_chunks(date(2026, 9, 1), date(2026, 9, 16))
    assert chunks[0][0] == date(2026, 9, 1)
    assert chunks[-1][1] == date(2026, 9, 17)
    assert all((end - start).days <= 7 for start, end in chunks)
    assert all(left[1] == right[0] for left, right in zip(chunks, chunks[1:]))


def test_cache_reuses_requested_session_from_a_different_manifest_range(tmp_path) -> None:
    cache = MarketDataCache(tmp_path, "yahoo")
    broad_start = datetime(2026, 9, 15, 13, 30, tzinfo=UTC)
    broad_end = datetime(2026, 9, 16, 20, 0, tzinfo=UTC)
    target = _bar(0)
    cache.store(
        "MEDS",
        "1m",
        (target,),
        start=broad_start,
        end=broad_end,
        query_profile="regular_session",
    )

    narrow = cache.load(
        "MEDS",
        "1m",
        start=OPEN,
        end=datetime(2026, 9, 16, 20, 0, tzinfo=UTC),
        query_profile="regular_session",
    )

    assert narrow == (target,)


def test_cache_still_rejects_a_missing_requested_session(tmp_path) -> None:
    cache = MarketDataCache(tmp_path, "yahoo")
    cache.store(
        "MEDS",
        "1m",
        (_bar(0),),
        start=OPEN,
        end=datetime(2026, 9, 16, 20, 0, tzinfo=UTC),
        query_profile="regular_session",
    )

    assert cache.load(
        "MEDS",
        "1m",
        start=datetime(2026, 9, 17, 13, 30, tzinfo=UTC),
        end=datetime(2026, 9, 17, 20, 0, tzinfo=UTC),
        query_profile="regular_session",
    ) is None


def test_replay_recovery_fills_twenty_minute_hole_from_factual_fallback() -> None:
    primary = tuple(_bar(index) for index in range(390) if not 10 <= index < 30)
    fallback = tuple(_bar(index, price="10.01") for index in range(10, 30))

    assert _needs_one_minute_recovery(
        "MEDS", [SESSION], primary, source="yahoo"
    ) is True

    recovered, unresolved = _recover_one_minute_sessions(
        "MEDS",
        [SESSION],
        primary_raw=primary,
        fallback_raw=fallback,
        primary_source="yahoo",
        fallback_source="alpaca-sip",
    )

    assert unresolved == {}
    assert len(recovered[SESSION]) == 390
    assert recovered[SESSION][9].open == Decimal("10")
    assert recovered[SESSION][10].open == Decimal("10.01")
    assert recovered[SESSION][29].open == Decimal("10.01")
    assert recovered[SESSION][30].open == Decimal("10")


def test_unrecoverable_one_minute_hole_stays_blocked_for_session_anchored_arms() -> None:
    primary = tuple(_bar(index) for index in range(390) if not 10 <= index < 30)

    recovered, unresolved = _recover_one_minute_sessions(
        "MEDS",
        [SESSION],
        primary_raw=primary,
        fallback_raw=(),
        primary_source="yahoo",
        fallback_source=None,
    )

    assert recovered[SESSION] == ()
    assert SESSION in unresolved
    assert "UNRESOLVED_1M_GAPS" in unresolved[SESSION]
