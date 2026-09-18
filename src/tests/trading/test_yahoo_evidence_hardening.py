from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.trading.market_evidence import (
    PremarketLiquidityEvidence,
    YAHOO_HARDENED_EVIDENCE_POLICY_VERSION,
    evidence_authorizes_feature,
    premarket_evidence_feature_compatible,
)
from app.trading.models import AdjustmentMode, MarketBar
from app.trading.service import TradingMarketDataService
from app.trading.yahoo_evidence import YahooEvidenceStore


ET = ZoneInfo("America/New_York")
INSTRUMENT = "equity:NASDAQ:TEST"


def _bar(session_date: date, minute: int, *, volume: str = "100", price: str = "10") -> MarketBar:
    start = datetime(
        session_date.year,
        session_date.month,
        session_date.day,
        9,
        30,
        tzinfo=ET,
    ).astimezone(timezone.utc) + timedelta(minutes=minute)
    value = Decimal(price)
    return MarketBar(
        instrument_id=INSTRUMENT,
        interval="1m",
        start_time=start,
        end_time=start + timedelta(minutes=1),
        open=value,
        high=value + Decimal("0.1"),
        low=value - Decimal("0.1"),
        close=value,
        volume=Decimal(volume),
        is_final=True,
        adjustment_mode=AdjustmentMode.RAW,
        session="regular",
        provider="yahoo",
        provider_event_id=str(int(start.timestamp())),
        received_at=start + timedelta(minutes=1, seconds=2),
    )


def _premarket_bar(session_date: date, minute: int, *, volume: str) -> MarketBar:
    start = datetime(
        session_date.year,
        session_date.month,
        session_date.day,
        4,
        0,
        tzinfo=ET,
    ).astimezone(timezone.utc) + timedelta(minutes=minute)
    return MarketBar(
        instrument_id=INSTRUMENT,
        interval="1m",
        start_time=start,
        end_time=start + timedelta(minutes=1),
        open=Decimal("10"),
        high=Decimal("10"),
        low=Decimal("10"),
        close=Decimal("10"),
        volume=Decimal(volume),
        is_final=True,
        adjustment_mode=AdjustmentMode.RAW,
        session="extended_pre",
        provider="yahoo",
        provider_event_id=str(int(start.timestamp())),
        received_at=start + timedelta(minutes=1, seconds=2),
    )


def test_yahoo_store_persists_and_reloads_finalized_one_minute_bars(tmp_path) -> None:
    store = YahooEvidenceStore(tmp_path)
    session_date = date(2026, 9, 17)
    bars = [_bar(session_date, 0), _bar(session_date, 1)]

    assert store.persist_market_bars(bars) == 2
    loaded = store.load_market_bars(
        INSTRUMENT,
        start=bars[0].start_time,
        end=bars[-1].end_time,
        session="regular",
    )

    assert [bar.start_time for bar in loaded] == [bar.start_time for bar in bars]
    assert all(bar.provider == "yahoo" for bar in loaded)


def test_yahoo_relative_rvol_uses_persistent_same_feed_baseline(tmp_path) -> None:
    store = YahooEvidenceStore(tmp_path)
    current = date(2026, 9, 17)
    historical_dates = [
        date(2026, 9, 16),
        date(2026, 9, 15),
        date(2026, 9, 14),
        date(2026, 9, 13),
        date(2026, 9, 12),
    ]
    for session_date in historical_dates:
        store.persist_market_bars(
            [
                _premarket_bar(session_date, 0, volume="50"),
                _premarket_bar(session_date, 1, volume="50"),
            ]
        )
    store.persist_market_bars(
        [
            _premarket_bar(current, 0, volume="100"),
            _premarket_bar(current, 1, volume="100"),
        ]
    )

    evidence = store.premarket_relative_volume(
        INSTRUMENT,
        datetime(2026, 9, 17, 4, 3, tzinfo=ET),
        minimum_baseline_sessions=5,
    )

    assert evidence.current_volume == Decimal("200")
    assert evidence.baseline_mean_volume == Decimal("100")
    assert evidence.relative_volume == Decimal("2")
    assert evidence.baseline_session_count == 5
    assert evidence.coverage_ratio == Decimal("1")


def test_hardened_yahoo_evidence_authorizes_relative_volume_not_consolidated() -> None:
    evidence = PremarketLiquidityEvidence(
        policy_version=YAHOO_HARDENED_EVIDENCE_POLICY_VERSION,
        provider="yahoo",
        feed="extended_hours",
        observed_at=datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc),
        current_premarket_volume=Decimal("1000"),
        current_premarket_dollar_volume=Decimal("10000"),
        tod_rvol=Decimal("5"),
        tod_rvol_numerator=Decimal("1000"),
        tod_rvol_denominator_mean=Decimal("200"),
        baseline_session_count=5,
        premarket_bar_count=10,
        nonzero_volume_bar_count=10,
        coverage_ratio=Decimal("1"),
        ready=True,
        volume_authority="provider_relative",
        volume_basis="yahoo_extended_hours",
        consolidated_volume_authority=False,
    )

    assert premarket_evidence_feature_compatible(evidence) is True
    assert evidence_authorizes_feature(evidence, "price_ohlc") is True
    assert evidence_authorizes_feature(evidence, "provider_relative_volume") is True
    assert evidence_authorizes_feature(evidence, "consolidated_volume") is False
    assert evidence_authorizes_feature(evidence, "live_bid_ask") is False
    assert evidence_authorizes_feature(evidence, "execution_fill") is False


class _YahooRepairProvider:
    def __init__(self, session_date: date) -> None:
        self.session_date = session_date
        self.calls = 0

    def get_intraday_bars_range(
        self,
        instrument_id,
        *,
        start,
        end,
        include_extended_hours=True,
        cancellation=None,
    ):
        self.calls += 1
        return SimpleNamespace(bars=[_bar(self.session_date, 1)])


class _RecoveryRegistry:
    def __init__(self, session_date: date) -> None:
        self.session_date = session_date
        self.primary_calls = 0
        self.iex_calls = 0
        self.yahoo = _YahooRepairProvider(session_date)

    def provider(self, provider_id):
        if provider_id == "yahoo":
            return self.yahoo
        return SimpleNamespace(provider_id=provider_id)

    def resolve_binding(self, instrument_id, binding_id=None):
        return SimpleNamespace(
            instrument_id=instrument_id,
            binding_id=binding_id or "yahoo:test",
            provider="yahoo",
        )

    def resolve_execution_binding(self, instrument_id, binding_id=None):
        return SimpleNamespace(
            instrument_id=instrument_id,
            binding_id="alpaca_iex:test",
            provider="alpaca_iex",
        )

    def bars(self, instrument_id, interval, limit, binding_id=None, cancellation=None):
        self.primary_calls += 1
        return SimpleNamespace(
            bars=[_bar(self.session_date, 0), _bar(self.session_date, 2)]
        )

    def execution_indicator_bars(self, *args, **kwargs):
        self.iex_calls += 1
        raise AssertionError("IEX fallback should not run after Yahoo exact repair")


def test_service_repairs_exact_yahoo_gap_before_iex_fallback(tmp_path) -> None:
    session_date = date(2026, 9, 17)
    registry = _RecoveryRegistry(session_date)
    service = TradingMarketDataService(
        registry=registry,
        yahoo_evidence_store=YahooEvidenceStore(tmp_path),
    )
    observed = datetime(2026, 9, 17, 9, 33, 10, tzinfo=ET)

    recovered = service.recovered_bars(
        INSTRUMENT,
        "1m",
        500,
        "yahoo:test",
        session_date=session_date,
        as_of=observed,
    )

    assert recovered.report.unresolved_gaps == ()
    assert [bar.start_time.astimezone(ET).minute for bar in recovered.bars] == [30, 31, 32]
    assert registry.yahoo.calls == 1
    assert registry.iex_calls == 0
    diagnostics = service.yahoo_evidence_store.diagnostics()
    assert diagnostics["repair_attempt_count"] == 1
    assert diagnostics["repair_success_count"] == 1
    assert diagnostics["repaired_bar_count"] == 1
