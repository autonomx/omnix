from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.assistant_tools.models import AssistantToolRequest
from app.assistant_tools.trading_adapter import run_trading_tool_request
from app.trading.execution import ExecutionObservation


class _FakeProvider:
    def execution_observation(self, instrument_id: str) -> ExecutionObservation:
        assert instrument_id == "equity:NASDAQ:NVDA"
        now = datetime.now(timezone.utc)
        return ExecutionObservation(
            instrument_id=instrument_id,
            binding_id="alpaca_iex:snapshot:equity:NASDAQ:NVDA",
            provider="alpaca_iex",
            bid=Decimal("100"),
            ask=Decimal("100.10"),
            last=Decimal("100.05"),
            source_time=now,
            received_at=now,
            session="regular",
            freshness_mode="live",
            execution_eligible=True,
        )


def test_trading_market_quote_adapter_is_read_only_and_source_timestamped() -> None:
    result = run_trading_tool_request(
        AssistantToolRequest(
            tool_id="trading",
            action_id="trading.market_quote",
            input={"ticker": "NVDA"},
        ),
        provider=_FakeProvider(),
    )
    assert result.error is None
    assert result.state_changed is False
    assert result.output["ticker"] == "NVDA"
    assert result.output["provider"] == "alpaca_iex"
    assert result.output["source_time"]
    assert result.output["authoritative_read_only"] is True


def test_trading_market_quote_requires_canonical_instrument() -> None:
    result = run_trading_tool_request(
        AssistantToolRequest(
            tool_id="trading",
            action_id="trading.market_quote",
            input={"ticker": "NOTAREALTICKER"},
        ),
        provider=_FakeProvider(),
    )
    assert result.error == "trading_instrument_not_resolved"
    assert result.state_changed is False
