from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.trading.finviz_gapper_discovery import (
    discover_finviz_gappers,
    parse_finviz_top_gainer_symbols,
)


class Response:
    def __init__(self, *, text="", payload=None):
        self.text = text
        self._payload = payload

    def json(self):
        return self._payload


class Runtime:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def test_parse_finviz_symbols_preserves_rank_and_deduplicates():
    html = """
    <a href="quote.ashx?t=FNGR&p=d">FNGR</a>
    <a href="/quote.ashx?t=QNRX">QNRX</a>
    <a href="quote.ashx?t=FNGR">FNGR duplicate</a>
    <a href="quote.ashx?t=PSQL&ty=c">PSQL</a>
    """
    assert parse_finviz_top_gainer_symbols(html) == ["FNGR", "QNRX", "PSQL"]


def _chart_payload(now: datetime):
    prior_open = now - timedelta(days=1, hours=5, minutes=50)
    current_pre = now - timedelta(minutes=2)
    timestamps = [
        int(prior_open.timestamp()),
        int((prior_open + timedelta(hours=6)).timestamp()),
        int(current_pre.timestamp()),
    ]
    return {
        "chart": {
            "result": [{
                "meta": {"exchangeName": "NMS", "regularMarketPrice": 12.0},
                "timestamp": timestamps,
                "indicators": {
                    "quote": [{
                        "close": [10.0, 10.0, 12.0],
                        "volume": [100, 100, 1000],
                    }]
                },
            }]
        }
    }


def test_finviz_discovery_uses_finviz_for_rank_and_yahoo_for_point_in_time_enrichment(monkeypatch):
    now = datetime.now(timezone.utc)
    finviz = Runtime([
        Response(text='<a href="quote.ashx?t=TEST">TEST</a>'),
    ])
    yahoo = Runtime([
        Response(payload=_chart_payload(now)),
        Response(payload={
            "quotes": [{
                "symbol": "TEST",
                "quoteType": "EQUITY",
                "exchange": "NMS",
                "marketCap": 50000000,
                "floatShares": 5000000,
                "bid": 11.95,
                "ask": 12.05,
            }]
        }),
    ])

    snapshot = discover_finviz_gappers(
        universe_id="finviz-test",
        evaluation_time=now,
        count=1,
        minimum_gap_pct=Decimal("10"),
        minimum_price=Decimal("1"),
        maximum_price=Decimal("20"),
        finviz_runtime=finviz,
        yahoo_runtime=yahoo,
    )

    assert snapshot.discovery_source == "finviz"
    assert len(snapshot.candidates) == 1
    candidate = snapshot.candidates[0]
    assert candidate.discovery_rank == 1
    assert candidate.instrument_id == "equity:NASDAQ:TEST"
    assert candidate.premarket_price == Decimal("12.0")
    assert candidate.previous_close == Decimal("10.0")
    assert candidate.gap_pct == Decimal("20.0")
    assert candidate.float_shares == Decimal("5000000")
    assert candidate.spread_bps is not None
    assert "finviz_top_gainers" in candidate.evidence_observed_at
