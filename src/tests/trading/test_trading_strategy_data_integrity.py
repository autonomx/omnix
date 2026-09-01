from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.trading.gapper_dataset import GapperCandidate, freeze_gapper_universe
from app.trading.models import MarketBar
from app.trading.strategy_data_integrity import (
    assess_universe_integrity,
    finviz_atomic_source_locator,
)
from app.trading.strategy_monitor import (
    _current_session_1m_integrity,
    _finalized_bars_for_session,
)


INSTRUMENT = "equity:NASDAQ:TEST"
SESSION = date(2026, 9, 1)
PREOPEN = datetime(2026, 9, 1, 13, 20, tzinfo=timezone.utc)
OPEN = datetime(2026, 9, 1, 13, 30, tzinfo=timezone.utc)


def candidate(*, complete: bool = True) -> GapperCandidate:
    return GapperCandidate(
        instrument_id=INSTRUMENT,
        binding_id="yahoo:historical_polling:equity:NASDAQ:TEST",
        observed_at=PREOPEN,
        evidence_observed_at={"finviz_top_gainers": PREOPEN},
        previous_close=Decimal("8"),
        premarket_price=Decimal("10"),
        gap_pct=Decimal("25"),
        premarket_volume=Decimal("50000"),
        premarket_dollar_volume=Decimal("500000"),
        premarket_bar_count=20 if complete else 0,
        tod_rvol=Decimal("5") if complete else None,
        market_data_complete=complete,
        data_quality_flags=() if complete else ("PREMARKET_BARS_MISSING", "TOD_RVOL_MISSING"),
        spread_bps=Decimal("40") if complete else None,
        discovery_rank=1,
    )


def bar(start: datetime) -> MarketBar:
    return MarketBar(
        instrument_id=INSTRUMENT,
        interval="1m",
        start_time=start,
        end_time=start + timedelta(minutes=1),
        open=Decimal("10"),
        high=Decimal("10.1"),
        low=Decimal("9.9"),
        close=Decimal("10"),
        volume=Decimal("1000"),
        is_final=True,
        session="regular",
        provider="fixture",
        received_at=start + timedelta(minutes=1),
    )


def test_legacy_paginated_finviz_archive_is_not_prospective_evidence() -> None:
    snapshot = freeze_gapper_universe(
        universe_id="legacy-finviz",
        session_date=SESSION,
        evaluation_time=PREOPEN,
        discovery_source="finviz",
        source_locator="https://finviz.com/screener?v=340&s=ta_topgainers",
        source_candidate_symbols=("TEST",),
        candidates=[candidate()],
    )

    integrity = assess_universe_integrity(snapshot)

    assert integrity.cohort_integrity == "invalid"
    assert integrity.cohort_complete is False
    assert integrity.prospective_eligible is False
    assert "FINVIZ_ATOMIC_COHORT_UNPROVEN" in integrity.reason_codes


def test_atomic_preopen_finviz_archive_is_prospectively_eligible() -> None:
    snapshot = freeze_gapper_universe(
        universe_id="atomic-finviz",
        session_date=SESSION,
        evaluation_time=PREOPEN,
        discovery_source="finviz",
        source_locator=finviz_atomic_source_locator(
            "https://finviz.com/screener?v=340&s=ta_topgainers"
        ),
        source_candidate_symbols=("TEST",),
        candidates=[candidate()],
    )

    integrity = assess_universe_integrity(snapshot)

    assert integrity.capture_on_time is True
    assert integrity.cohort_complete is True
    assert integrity.cohort_integrity == "valid"
    assert integrity.market_data_complete is True
    assert integrity.prospective_eligible is True


def test_candidate_market_data_incomplete_does_not_invalidate_atomic_source_cohort() -> None:
    snapshot = freeze_gapper_universe(
        universe_id="atomic-incomplete-candidate",
        session_date=SESSION,
        evaluation_time=PREOPEN,
        discovery_source="finviz",
        source_locator=finviz_atomic_source_locator(
            "https://finviz.com/screener?v=340&s=ta_topgainers"
        ),
        source_candidate_symbols=("TEST",),
        candidates=[candidate(complete=False)],
    )

    integrity = assess_universe_integrity(snapshot)

    assert integrity.prospective_eligible is True
    assert integrity.market_data_complete is False
    assert "CANDIDATE_MARKET_DATA_INCOMPLETE" in integrity.reason_codes


def test_session_filter_never_uses_previous_day_bars() -> None:
    prior = bar(datetime(2026, 8, 31, 13, 30, tzinfo=timezone.utc))
    current = bar(OPEN)

    filtered = _finalized_bars_for_session([prior, current], SESSION)

    assert filtered == [current]


def test_current_session_integrity_requires_the_opening_minute() -> None:
    missing_open = [bar(OPEN + timedelta(minutes=30))]
    ready = [bar(OPEN), bar(OPEN + timedelta(minutes=1))]

    assert _current_session_1m_integrity(
        [],
        session_date=SESSION,
        observed_at=PREOPEN,
    ) == (False, "CURRENT_SESSION_NOT_STARTED")
    assert _current_session_1m_integrity(
        missing_open,
        session_date=SESSION,
        observed_at=OPEN + timedelta(minutes=31),
    ) == (False, "OPENING_1M_HISTORY_INCOMPLETE")
    assert _current_session_1m_integrity(
        ready,
        session_date=SESSION,
        observed_at=OPEN + timedelta(minutes=2),
    ) == (True, "CURRENT_SESSION_1M_READY")
