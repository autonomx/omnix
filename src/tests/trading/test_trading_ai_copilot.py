"""TradingView's other AI features (2026-11), read-only in Omnix: Chart Copilot, AI news digest, AI filing summaries.

What the model returns is a proposal: Copilot's chart changes pass Omnix's checks or are dropped, cited headlines are
only ones Omnix supplied, and a filing's figures stay only when its text contains them word for word.
"""

from __future__ import annotations

import json
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.apps.trading.research.chart_copilot import CopilotRequest, chart_copilot, checked_actions
from app.apps.trading.research.filing_summaries import (
    FilingSummaries,
    FilingSummaryRequest,
    document_text,
    excerpt,
    filings_from_submissions,
    press_release_name,
    verified_figures,
)
from app.apps.trading.research.news_digest import NewsDigestRequest, news_digest
from app.apps.trading.research.range_research import RangeHeadline
from app.apps.trading.research_api import create_trading_research_router
from app.apps.trading.sec_contact import SecContactRequired
from src.tests.trading.test_trading_ai_range import ChartService, ScriptedProvider
from src.tests.trading.test_trading_phase14_research import INSTRUMENT, NOW, bars_response


def copilot_request(**overrides) -> CopilotRequest:
    values = {
        "instrument_id": INSTRUMENT, "interval": "1d", "messages": [{"role": "user", "content": "Where is support?"}],
        "indicators": [{"id": "sma", "period": 20}], "supported_intervals": ["1h", "4h", "1d"],
    }
    return CopilotRequest.model_validate({**values, **overrides})


def headline(index: int, when=NOW) -> RangeHeadline:
    return RangeHeadline(id=f"n{index}", headline=f"Headline {index}", source="benzinga", url=f"https://news.example/{index}", created_at=when)


# -- Chart Copilot ---------------------------------------------------------------------------------------------


def test_copilot_keeps_only_chart_changes_that_pass_omnix_checks():
    bars = bars_response(120).bars
    low, high = min(bar.low for bar in bars), max(bar.high for bar in bars)
    actions, dropped = checked_actions([
        {"kind": "set_interval", "interval": "4h"},
        {"kind": "set_interval", "interval": "3m"},  # the feed doesn't offer it
        {"kind": "set_interval", "interval": "1d"},  # already showing
        {"kind": "add_indicator", "indicator": "ema", "period": 50},
        {"kind": "add_indicator", "indicator": "ichimoku"},  # not one Omnix offers here
        {"kind": "remove_indicator", "indicator": "rsi"},  # not on the chart
        {"kind": "draw_level", "price": str(low * 3 + high)},  # far outside the bars
        {"kind": "place_order", "side": "buy"},
    ], copilot_request(), bars)
    assert [(action.kind, action.label) for action in actions] == [("set_interval", "Switch to 4h"), ("add_indicator", "Add EMA 50")]
    assert dropped == 6

    actions, _ = checked_actions([
        {"kind": "draw_level", "price": str(low), "note": "  swing   low "},
        {"kind": "mark_range", "start": bars[80].start_time.isoformat(), "end": bars[60].start_time.isoformat()},
        {"kind": "remove_indicator", "indicator": "sma"},
        {"kind": "add_indicator", "indicator": "macd", "period": 12},
    ], copilot_request(), bars)
    level, marked, removed, macd = actions
    assert level.price == low and level.time == bars[-1].start_time and level.note == "swing low" and level.label.endswith("· swing low")
    # A span drawn backwards is ordered, on the bars' own times.
    assert (marked.start, marked.end) == (bars[60].start_time, bars[80].start_time)
    assert removed.label == "Remove SMA"
    assert macd.period is None and macd.label == "Add MACD"


def test_copilot_answers_from_the_chart_and_cites_only_supplied_headlines():
    provider = ScriptedProvider({
        "reply": "Support sits near the recent low.", "points": ["Volume faded."],
        "actions": [{"kind": "set_interval", "interval": "4h"}], "cited": ["h2", "h9"],
    })
    news_calls = []

    def news(symbol, start, end):
        news_calls.append((symbol, end - start))
        return [headline(1), headline(2)]

    result = chart_copilot(copilot_request(), market_service_factory=ChartService, provider_factory=lambda: provider, news=news)
    assert result.reply == "Support sits near the recent low."
    assert [item.id for item in result.headlines] == ["n2"]
    assert [action.interval for action in result.actions] == ["4h"]
    assert news_calls == [("BTCUSD", timedelta(days=3))]
    assert result.facts.bars == 50 and result.read_only
    sent = json.loads(provider.messages[1].content)
    assert sent["conversation"][-1] == {"role": "user", "content": "Where is support?"}
    assert sent["chart"]["indicators"] == [{"id": "sma", "period": 20}]
    # The model never sees a headline's link.
    assert "news.example" not in provider.messages[1].content


def test_copilot_conversation_must_end_with_the_person():
    with pytest.raises(ValidationError, match="end with your message"):
        copilot_request(messages=[{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}])


# -- AI news digest --------------------------------------------------------------------------------------------


def test_news_digest_groups_headlines_and_skips_the_model_without_any(monkeypatch):
    instrument = SimpleNamespace(asset_class=bars_response(1).instrument.asset_class, display_symbol="BTC/USDT", base_currency="BTC", name="Bitcoin")
    monkeypatch.setattr("app.apps.trading.research.news_digest.instrument_by_id", lambda _id: instrument)
    provider = ScriptedProvider({
        "title": "ETF demand", "summary": "Flows dominated the news.", "tone": "bullish",
        "themes": [{"title": "ETF flows", "summary": "Inflows rose.", "cited": ["h1", "h7"]}, {"title": "", "summary": "x"}],
    })
    seen = []

    def news(symbol, start, end):
        seen.append((symbol, end - start))
        return [headline(1), headline(2)]

    result = news_digest(NewsDigestRequest(instrument_id=INSTRUMENT, window="24h"), provider_factory=lambda: provider, news=news, clock=lambda: NOW)
    assert seen == [("BTCUSD", timedelta(hours=24))]
    assert [theme.title for theme in result.themes] == ["ETF flows"]
    assert [item.id for item in result.themes[0].headlines] == ["n1"]
    # A tone outside the four readings is not shown.
    assert result.tone is None and result.headlines_considered == 2

    untouched = ScriptedProvider({})
    empty = news_digest(NewsDigestRequest(instrument_id=INSTRUMENT), provider_factory=lambda: untouched, news=lambda *_: [], clock=lambda: NOW)
    assert empty.news_status == "none" and "BTCUSD" in empty.summary and untouched.messages == [] and empty.provider is None


# -- AI filing summaries ---------------------------------------------------------------------------------------


SUBMISSIONS = {
    "cik": "0000320193", "name": "Apple Inc.",
    "filings": {"recent": {
        "form": ["8-K", "4", "10-Q", "10-K"],
        "accessionNumber": ["0000320193-26-000010", "0000320193-26-000009", "0000320193-26-000008", "0000320193-25-000100"],
        "filingDate": ["2026-10-30", "2026-10-29", "2026-08-01", "2025-11-01"],
        "reportDate": ["2026-10-30", "", "2026-06-28", "2025-09-27"],
        "primaryDocument": ["aapl-8k.htm", "form4.xml", "aapl-10q.htm", "aapl-10k.htm"],
        "primaryDocDescription": ["8-K", "", "10-Q", "10-K"],
        "items": ["2.02,9.01", "", "", ""],
    }},
}


class Documents:
    def __init__(self) -> None:
        self.fetched: list[str] = []

    def submissions(self, cik):
        assert cik == "0000320193"
        return SUBMISSIONS

    def text(self, url):
        self.fetched.append(url)
        if url.endswith("ex991.htm"):
            return "<html><body><p>Revenue was $94.9 billion, up 6%.</p></body></html>"
        return "<html><head><style>p{}</style></head><body><ix:header>hidden 123</ix:header><div>Item 2.02 Results&nbsp;of Operations</div></body></html>"

    def folder(self, cik, accession):
        return ["aapl-8k.htm", "aapl-ex991.htm", "R1.htm"]


class Profiles:
    def ensure(self, tickers, max_new=40):
        return {"AAPL": SimpleNamespace(cik="0000320193", name="Apple")}


def test_filings_list_the_company_reports_newest_first():
    filings = filings_from_submissions(SUBMISSIONS)
    assert [filing.form for filing in filings] == ["8-K", "10-Q", "10-K"]
    assert filings[0].url == "https://www.sec.gov/Archives/edgar/data/320193/000032019326000010/aapl-8k.htm"
    assert filings[0].items == ["2.02", "9.01"]
    assert press_release_name(["aapl-8k.htm", "R1.htm", "aapl-ex99_1.htm"], "aapl-8k.htm") == "aapl-ex99_1.htm"


def test_filing_text_drops_markup_and_long_reports_are_read_by_section():
    assert document_text("<style>x</style><ix:header>99</ix:header><p>Net&nbsp;sales</p><p>rose</p>") == "Net sales\nrose"
    toc = "Table of contents Item 1. Business Item 1A. Risk Factors Item 7. Management's Discussion and Analysis Item 8."
    body = "x" * 7_000 + " Risk Factors " + "r" * 20_000 + " Management's Discussion and Analysis " + "m" * 40_000
    read = excerpt(toc + body, "10-K", limit=12_000)
    assert len(read) <= 12_010
    assert "Risk Factors rrr" in read and "Management's Discussion and Analysis mmm" in read
    assert excerpt("short", "8-K") == "short"


def test_filing_figures_are_kept_only_when_the_text_contains_them():
    figures, dropped = verified_figures([
        {"label": "Revenue", "value": "$94.9  billion"}, {"label": "Margin", "value": "47%"}, {"label": "Note", "value": "strong"},
    ], "Revenue was $94.9 billion, up 6%.")
    assert [(figure.label, figure.value) for figure in figures] == [("Revenue", "$94.9 billion")]
    assert dropped == 2


def test_filing_summary_reads_the_report_and_its_press_release_once():
    provider = ScriptedProvider({
        "title": "Q4 results", "summary": "Apple reported results.", "highlights": ["Revenue grew."], "risks": [],
        "figures": [{"label": "Revenue", "value": "$94.9 billion"}, {"label": "EPS", "value": "$1.85"}],
    })
    documents = Documents()
    service = FilingSummaries(documents_factory=lambda: documents, profiles=lambda: Profiles(), provider_factory=lambda: provider)
    request = FilingSummaryRequest(instrument_id="equity:NASDAQ:AAPL", accession="0000320193-26-000010")
    result = service.summary(request)
    assert [source.name for source in result.documents] == ["aapl-8k.htm", "aapl-ex991.htm"]
    assert [figure.value for figure in result.figures] == ["$94.9 billion"] and result.figures_dropped == 1
    sent = json.loads(provider.messages[1].content)
    assert "hidden 123" not in sent["text"] and "Revenue was $94.9 billion" in sent["text"]
    assert service.summary(request) is result and len(documents.fetched) == 2
    with pytest.raises(ValueError, match="not one of this company's recent reports"):
        service.summary(FilingSummaryRequest(instrument_id="equity:NASDAQ:AAPL", accession="0000320193-26-000009"))
    with pytest.raises(ValueError, match="US stocks"):
        service.filings(INSTRUMENT)


def test_routes_answer_and_name_a_missing_sec_contact():
    provider = ScriptedProvider({"reply": "Up on the day.", "points": [], "actions": [], "cited": []})

    class NoContact:
        def ensure(self, tickers, max_new=40):
            raise SecContactRequired()

    app = FastAPI()
    app.include_router(create_trading_research_router(
        market_service_factory=ChartService, provider_factory=lambda: provider,
        filing_summaries=FilingSummaries(documents_factory=Documents, profiles=lambda: NoContact(), provider_factory=lambda: provider),
    ))
    client = TestClient(app)
    answered = client.post("/api/trading/research/copilot", json=copilot_request().model_dump(mode="json"))
    assert answered.status_code == 200 and answered.json()["reply"] == "Up on the day."
    refused = client.get("/api/trading/research/filings", params={"instrument_id": "equity:NASDAQ:AAPL"})
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "sec_contact_required"
    bad = client.post("/api/trading/research/filings/summary", json={"instrument_id": "equity:NASDAQ:AAPL", "accession": "../etc"})
    assert bad.status_code == 422
