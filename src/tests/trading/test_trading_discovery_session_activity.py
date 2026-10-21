"""Live leaderboard observations score the day's activity after the open, not the premarket alone."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.apps.trading import strategy_discovery_acquisition as acquisition
from app.apps.trading.gapper_dataset import GapperCandidate
from app.apps.trading.models import MarketBar

SESSION = date(2026, 10, 20)
OPEN = datetime(2026, 10, 20, 13, 30, tzinfo=timezone.utc)


def _bar(minute: int, *, close: str = "2.50", volume: str = "1000") -> MarketBar:
    start = OPEN + timedelta(minutes=minute)
    return MarketBar(
        instrument_id="equity:AMEX:HOST", interval="1m", start_time=start, end_time=start + timedelta(minutes=1),
        open=Decimal(close), high=Decimal(close), low=Decimal(close), close=Decimal(close),
        volume=Decimal(volume), is_final=True, session="regular", provider="yahoo", received_at=start,
    )


def test_leaderboard_features_count_the_regular_session_after_the_open(monkeypatch) -> None:
    observed = OPEN + timedelta(hours=4, minutes=10)  # 13:40 ET
    candidate = GapperCandidate(
        instrument_id="equity:AMEX:HOST", previous_close=Decimal("1.86"), premarket_price=Decimal("2.70"),
        gap_pct=Decimal("45"), premarket_volume=Decimal("0"), premarket_dollar_volume=Decimal("0"),
        float_shares=Decimal("10000000"), observed_at=observed, discovery_rank=4,
    )
    snapshot = SimpleNamespace(
        candidates=[candidate], evaluation_time=observed, session_date=SESSION,
        source_locator="https://finviz.com/screener",
    )
    monkeypatch.setattr(acquisition, "discover_finviz_gappers", lambda **kwargs: snapshot)
    requested: list[tuple] = []

    class _Store:
        def load_market_bars(self, instrument_id, *, start, end, session=None, **kwargs):
            requested.append((instrument_id, start, end, session))
            return [_bar(0, close="2.50", volume="2000000"), _bar(1, close="2.60", volume="1000000")]

    from app.apps.trading import yahoo_evidence

    monkeypatch.setattr(yahoo_evidence, "default_yahoo_evidence_store", lambda: _Store())
    [row] = acquisition.FinvizLiveLeaderSource().capture(observed_at=observed)

    # HOST recorded $0 all day before: the premarket figure, not the session's.
    assert row.market.dollar_volume == 2_000_000 * 2.50 + 1_000_000 * 2.60
    assert row.market.volume_to_float == 0.3
    assert requested == [("equity:AMEX:HOST", OPEN, observed, "regular")]

    premarket = OPEN - timedelta(minutes=30)
    early = candidate.model_copy(update={
        "observed_at": premarket, "premarket_volume": Decimal("1000"), "premarket_dollar_volume": Decimal("2000"),
    })
    snapshot.candidates, snapshot.evaluation_time = [early], premarket
    [row] = acquisition.FinvizLiveLeaderSource().capture(observed_at=premarket)
    assert row.market.dollar_volume == 2000.0  # before the open: the premarket figure alone
