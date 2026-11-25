"""AI Range (2026-11): the span's facts are Omnix's, the model only phrases them and cites supplied headlines."""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.apps.trading.models import AssetClass
from app.apps.trading.research.range_research import (
    RangeHeadline,
    RangeResearchRequest,
    news_symbol,
    prompt_bars,
    range_facts,
    research_range,
)
from app.apps.trading.research_api import create_trading_research_router
from src.tests.trading.test_trading_phase14_research import INSTRUMENT, NOW, bars_response


class ChartService:
    """The chart's bars request, as the AI Range call must repeat it."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def bars(self, instrument_id, interval, limit, binding_id=None, *, alignment="count", include_extended_hours=True):
        self.calls.append((instrument_id, interval, limit, binding_id, alignment, include_extended_hours))
        return bars_response(min(limit, 120))


class ScriptedProvider:
    name = "scripted"
    model = "scripted-model"

    def __init__(self, reply: dict) -> None:
        self.reply = reply
        self.messages: list = []

    def chat_completion(self, messages, model=None, stream=False, **kwargs):
        self.messages = messages
        return json.dumps(self.reply)


def request(**overrides) -> RangeResearchRequest:
    values = {
        "instrument_id": INSTRUMENT, "interval": "1d", "action": "explain",
        "start": (NOW + timedelta(days=60)).isoformat(), "end": (NOW + timedelta(days=79)).isoformat(),
        "history_limit": 500,
    }
    return RangeResearchRequest.model_validate({**values, **overrides})


def headline(index: int, hours: int) -> RangeHeadline:
    return RangeHeadline(
        id=f"n{index}", headline=f"Headline {index}", source="benzinga", url=f"https://news.example/{index}",
        created_at=NOW + timedelta(days=60, hours=hours),
    )


def test_facts_measure_only_the_bars_inside_the_span():
    bars = bars_response(120).bars
    facts, inside = range_facts(bars, bars[60].start_time, bars[79].start_time)
    assert facts.bars == len(inside) == 20
    assert (facts.open, facts.close) == (bars[60].open, bars[79].close)
    assert facts.high == bars[79].high and facts.high_time == bars[79].start_time
    assert facts.low == bars[60].low
    assert facts.volume == sum((bar.volume for bar in inside), Decimal("0"))
    # The 20 bars before the span set the volume comparison and the prior move.
    assert facts.volume_vs_prior is not None and facts.volume_vs_prior > 1
    assert facts.prior_change_percent is not None
    assert facts.sma_20_end is not None and facts.rsi_14_end is not None
    with pytest.raises(ValueError, match="no bars"):
        range_facts(bars, bars[-1].end_time + timedelta(days=5), bars[-1].end_time + timedelta(days=9))


def test_long_spans_are_merged_for_the_prompt_without_losing_extremes():
    bars = bars_response(120).bars
    rows = prompt_bars(bars, limit=40)
    assert len(rows) == 40
    assert rows[0]["open"] == str(bars[0].open) and rows[-1]["close"] == str(bars[-1].close)
    assert max(Decimal(row["high"]) for row in rows) == max(bar.high for bar in bars)
    assert sum(Decimal(row["volume"]) for row in rows) == sum((bar.volume for bar in bars), Decimal("0"))


def test_news_symbols_follow_alpaca_tags():
    assert news_symbol(SimpleNamespace(asset_class=AssetClass.EQUITY, display_symbol="aapl", base_currency=None)) == "AAPL"
    assert news_symbol(SimpleNamespace(asset_class=AssetClass.CRYPTO, display_symbol="BTC/USDT", base_currency="BTC")) == "BTCUSD"
    assert news_symbol(SimpleNamespace(asset_class=AssetClass.ECONOMIC, display_symbol="CPI", base_currency=None)) is None


def test_answer_keeps_only_cited_headlines_omnix_supplied():
    service = ChartService()
    provider = ScriptedProvider({
        "title": "A steady climb", "summary": "Price rose across the span on rising volume.",
        "points": ["Closed near the high.", "  ", "Volume above the prior span."],
        "cited": ["h2", "h9", "https://made.up/story", "h2"],
    })
    asked_news = []

    def news(symbol, start, end):
        asked_news.append((symbol, start, end))
        return [headline(1, 2), headline(2, 30)]

    result = research_range(
        request(alignment="clock", extended_hours=False), market_service_factory=lambda: service,
        provider_factory=lambda: provider, news=news, events=lambda _id: [],
    )
    # The chart's own bars request, so the span is measured on what the person sees.
    assert service.calls == [(INSTRUMENT, "1d", 500, None, "clock", False)]
    assert asked_news[0][0] == "BTCUSD"
    assert [item.id for item in result.headlines] == ["n2"]
    assert result.headlines[0].url == "https://news.example/2"
    assert result.points == ["Closed near the high.", "Volume above the prior span."]
    assert result.news_status == "ok" and result.headlines_considered == 2
    assert result.facts.bars == 20 and result.read_only is True
    sent = json.loads(provider.messages[1].content)
    assert sent["action"] == "explain"
    assert [item["id"] for item in sent["headlines"]] == ["h1", "h2"]
    assert "url" not in sent["headlines"][0]  # links stay Omnix's; the model sees ids and text


def test_technicals_skip_news_and_a_failed_news_source_is_reported():
    provider = ScriptedProvider({"title": "t", "summary": "s.", "points": [], "cited": []})

    def failing(*_args):
        raise RuntimeError("no credentials")

    technicals = research_range(
        request(action="technicals"), market_service_factory=ChartService, provider_factory=lambda: provider,
        news=failing, events=failing,
    )
    assert technicals.news_status == "not_used"
    explained = research_range(
        request(), market_service_factory=ChartService, provider_factory=lambda: provider, news=failing, events=failing,
    )
    assert explained.news_status == "unavailable" and explained.headlines == []


def test_ask_needs_a_question_and_reversed_anchors_are_ordered():
    with pytest.raises(ValidationError, match="question"):
        request(action="ask", question="  ")
    flipped = request(start=(NOW + timedelta(days=79)).isoformat(), end=(NOW + timedelta(days=60)).isoformat())
    assert flipped.start < flipped.end


def test_route_answers_and_maps_an_empty_span_to_a_request_error():
    provider = ScriptedProvider({"title": "t", "summary": "A summary.", "points": ["p"], "cited": []})
    app = FastAPI()
    app.include_router(create_trading_research_router(market_service_factory=ChartService, provider_factory=lambda: provider))
    client = TestClient(app)
    body = request(action="technicals").model_dump(mode="json")
    answered = client.post("/api/trading/research/range", json=body)
    assert answered.status_code == 200, answered.text
    assert answered.json()["disclaimer"].startswith("Research only.")
    empty = client.post("/api/trading/research/range", json={**body, "start": "2030-01-01T00:00:00Z", "end": "2030-01-05T00:00:00Z"})
    assert empty.status_code == 422
    assert empty.json()["detail"]["code"] == "invalid_research_request"
